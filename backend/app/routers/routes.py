import gzip
import json
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.routing import APIRoute

from app.core.redis import RouteCache, SegmentCache, DeadPairCache
from app.core.dates import validate_journey_date
from app.core.manifest_store import (
    RouteManifestEntry,
    SeatFinderEntry,
    TrainSearchEntry,
)
from app.core.pairs import enumerate_covering_pairs
from app.dependencies import ManifestStoreDep, StationDirectoryDep
from app.exceptions import ProviderUnavailableError, TrainNotFoundError
from app.providers.irctc.client import (
    build_confirmtkt_descriptor,
    build_erail_header_descriptor,
    build_erail_route_descriptor,
    format_date,
    parse_erail_header,
    parse_erail_route,
)
from app.providers.irctc.provider import build_quota_rows, build_raw_trains_between
from app.providers.prefetched.provider import PreFetchedProvider
from app.schemas import (
    BookingQuota,
    ManifestResponse,
    ProcessRequest,
    QuotaSearchManifestRequest,
    RouteManifestRequest,
    SeatFinderManifestRequest,
    Station,
    StationStop,
    TrainQuotaClasses,
    TrainRoute,
    TrainsBetweenResponse,
    TrainSearchManifestRequest,
    TrainsQuotaAvailabilityResponse,
)
from app.services.recommendations import RecommendationService
from app.services.train_search import to_class, to_train_between


class GzipRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            if "gzip" in request.headers.getlist("Content-Encoding"):
                body = await request.body()
                try:
                    decompressed_body = gzip.decompress(body)
                except gzip.BadGzipFile:
                    raise HTTPException(status_code=400, detail="Invalid gzip payload")

                async def receive():
                    return {"type": "http.request", "body": decompressed_body}

                request = Request(request.scope, receive)
            return await original_route_handler(request)

        return custom_route_handler


router = APIRouter(prefix="/api", route_class=GzipRoute)

# --- Route Lookup ---


@router.post("/route/manifest", response_model=ManifestResponse | TrainRoute)
async def route_manifest(body: RouteManifestRequest, store: ManifestStoreDep):
    cached = await RouteCache.get(body.train_number)
    if cached:
        return cached

    entry = RouteManifestEntry(train_number=body.train_number)
    mid = store.put(entry)
    return ManifestResponse(
        manifest_id=mid, fetches=[build_erail_header_descriptor(body.train_number)]
    )


@router.post("/route/process", response_model=ManifestResponse | TrainRoute)
async def route_process(body: ProcessRequest, store: ManifestStoreDep):
    entry = store.pop(body.manifest_id)
    if not isinstance(entry, RouteManifestEntry):
        raise HTTPException(404, "Manifest expired or unknown")

    if not body.results:
        raise HTTPException(400, "Missing results")
    result = body.results[0]

    if entry.phase == "header":
        parsed = parse_erail_header(result.body)
        if parsed is None:
            raise TrainNotFoundError(entry.train_number)
        train_id, train_no, train_name = parsed
        entry.phase = "route"
        entry.train_id = train_id
        entry.train_no = train_no
        entry.train_name = train_name
        mid = store.put(entry)
        return ManifestResponse(
            manifest_id=mid, fetches=[build_erail_route_descriptor(train_id)]
        )

    elif entry.phase == "route":
        stops = parse_erail_route(result.body)
        if not stops:
            raise ProviderUnavailableError(
                "erail TRAINROUTE returned no parseable stops"
            )
        route = TrainRoute(
            train_number=entry.train_number,
            train_name=entry.train_name or "",
            stations=[StationStop(**s) for s in stops],
        )
        await RouteCache.put(entry.train_number, route)
        return route


# --- Seat Finder ---


@router.post("/seat-finder/manifest")
async def seat_finder_manifest(
    body: SeatFinderManifestRequest, store: ManifestStoreDep
):
    validate_journey_date(body.date)
    source = body.user_source.strip().upper()
    destination = body.user_destination.strip().upper()

    cached_route = await RouteCache.get(body.train_number)
    if cached_route:
        all_pairs = enumerate_covering_pairs(cached_route, source, destination)
        pairs = []
        for b, a in all_pairs:
            if not await DeadPairCache.get(body.train_number, b.code, a.code):
                pairs.append((b, a))
        fetch_group = (
            body.quota.value
            if body.quota in (BookingQuota.LADIES, BookingQuota.SENIOR)
            else None
        )
        date_str = format_date(body.date)
        cached_segs: dict[str, list[dict]] = {}
        fetches = []
        fetch_id_to_pair = {}
        for b, a in pairs:
            fid = f"{b.code}|{a.code}"
            fetch_id_to_pair[fid] = (b, a)
            hit = await SegmentCache.get(b.code, a.code, date_str, fetch_group)
            if hit is not None:
                cached_segs[fid] = hit
            else:
                fetches.append(
                    build_confirmtkt_descriptor(
                        b.code, a.code, body.date, body.quota, fid
                    )
                )

        entry = SeatFinderEntry(
            phase="fetch",
            route=cached_route,
            pairs=pairs,
            fetch_id_to_pair=fetch_id_to_pair,
            cached_segments=cached_segs or None,
            train_number=body.train_number,
            user_source=source,
            user_destination=destination,
            journey_date=body.date,
            travel_class=body.travel_class,
            quota=body.quota,
        )

        if not fetches:
            provider = PreFetchedProvider(entry, cached_segs)
            return await RecommendationService(provider).find_optimal_route(
                cached_route.train_number,
                source,
                destination,
                body.date,
                body.travel_class,
                body.quota,
            )

        mid = store.put(entry)
        return ManifestResponse(manifest_id=mid, fetches=fetches)

    entry = SeatFinderEntry(
        phase="header",
        train_number=body.train_number,
        user_source=source,
        user_destination=destination,
        journey_date=body.date,
        travel_class=body.travel_class,
        quota=body.quota,
    )
    mid = store.put(entry)
    return ManifestResponse(
        manifest_id=mid, fetches=[build_erail_header_descriptor(body.train_number)]
    )


@router.post("/seat-finder/process")
async def seat_finder_process(body: ProcessRequest, store: ManifestStoreDep):
    entry = store.pop(body.manifest_id)
    if not isinstance(entry, SeatFinderEntry):
        raise HTTPException(404, "Manifest expired or unknown")

    if entry.phase == "header":
        if not body.results:
            raise HTTPException(400, "Missing results")
        parsed = parse_erail_header(body.results[0].body)
        if parsed is None:
            raise TrainNotFoundError(entry.train_number)
        entry.train_id, entry.train_no, entry.train_name = parsed
        entry.phase = "route"
        mid = store.put(entry)
        if entry.train_id is None:
            raise HTTPException(500, "Parsed train_id is None")
        return ManifestResponse(
            manifest_id=mid, fetches=[build_erail_route_descriptor(entry.train_id)]
        )

    elif entry.phase == "route":
        if not body.results:
            raise HTTPException(400, "Missing results")
        stops = parse_erail_route(body.results[0].body)
        if not stops:
            raise ProviderUnavailableError(
                "erail TRAINROUTE returned no parseable stops"
            )
        route = TrainRoute(
            train_number=entry.train_number,
            train_name=entry.train_name or "",
            stations=[StationStop(**s) for s in stops],
        )
        await RouteCache.put(entry.train_number, route)
        all_pairs = enumerate_covering_pairs(
            route, entry.user_source, entry.user_destination
        )
        pairs = []
        for b, a in all_pairs:
            if not await DeadPairCache.get(entry.train_number, b.code, a.code):
                pairs.append((b, a))
        fetch_group = (
            entry.quota.value
            if entry.quota in (BookingQuota.LADIES, BookingQuota.SENIOR)
            else None
        )
        date_str = format_date(entry.journey_date)

        cached_segs: dict[str, list[dict]] = {}
        fetches = []
        fetch_id_to_pair = {}
        for b, a in pairs:
            fid = f"{b.code}|{a.code}"
            fetch_id_to_pair[fid] = (b, a)
            hit = await SegmentCache.get(b.code, a.code, date_str, fetch_group)
            if hit is not None:
                cached_segs[fid] = hit
            else:
                fetches.append(
                    build_confirmtkt_descriptor(
                        b.code, a.code, entry.journey_date, entry.quota, fid
                    )
                )

        entry.route = route
        entry.pairs = pairs
        entry.fetch_id_to_pair = fetch_id_to_pair
        entry.cached_segments = cached_segs or None

        if not fetches:
            provider = PreFetchedProvider(entry, cached_segs)
            return await RecommendationService(provider).find_optimal_route(
                route.train_number,
                entry.user_source,
                entry.user_destination,
                entry.journey_date,
                entry.travel_class,
                entry.quota,
            )

        entry.phase = "fetch"
        mid = store.put(entry)
        return ManifestResponse(manifest_id=mid, fetches=fetches)

    elif entry.phase == "fetch":
        if entry.fetch_id_to_pair is None or entry.route is None:
            raise HTTPException(500, "Missing pairs or route in entry")

        submitted_ids = [r.fetch_id for r in body.results]
        submitted_set = set(submitted_ids)
        if len(submitted_ids) != len(submitted_set):
            raise HTTPException(400, "Duplicate fetch_id")
        if not submitted_set <= set(entry.fetch_id_to_pair.keys()):
            raise HTTPException(400, "Unknown fetch_id")

        for fetch_id, (board, alight) in entry.fetch_id_to_pair.items():
            if fetch_id not in submitted_set:
                await DeadPairCache.put(entry.train_number, board.code, alight.code)

        fetch_group = (
            entry.quota.value
            if entry.quota in (BookingQuota.LADIES, BookingQuota.SENIOR)
            else None
        )
        date_str = format_date(entry.journey_date)
        parsed_segments: dict[str, list[dict]] = {}

        for r in body.results:
            train_list: list[dict] = []
            if r.status == 200 and r.body:
                try:
                    payload = json.loads(r.body)
                    data = payload.get("data") if isinstance(payload, dict) else None
                    train_list = (
                        (data or {}).get("trainList", [])
                        if isinstance(data, dict)
                        else []
                    )
                except (json.JSONDecodeError, AttributeError):
                    pass
            parsed_segments[r.fetch_id] = train_list
            board, alight = r.fetch_id.split("|")
            if train_list:
                await SegmentCache.put(board, alight, date_str, fetch_group, train_list)

        if entry.cached_segments:
            parsed_segments.update(entry.cached_segments)

        provider = PreFetchedProvider(entry, parsed_segments)
        return await RecommendationService(provider).find_optimal_route(
            entry.route.train_number,
            entry.user_source,
            entry.user_destination,
            entry.journey_date,
            entry.travel_class,
            entry.quota,
        )


# --- Train Search ---


@router.post("/trains-between/manifest")
async def trains_between_manifest(
    body: TrainSearchManifestRequest, store: ManifestStoreDep
):
    validate_journey_date(body.date)
    source = body.source.strip().upper()
    destination = body.destination.strip().upper()
    date_str = format_date(body.date)

    cached = await SegmentCache.get(source, destination, date_str, None)
    if cached is not None:
        raw_trains = build_raw_trains_between(cached)
        return TrainsBetweenResponse(
            source=source,
            destination=destination,
            journey_date=body.date,
            trains=[to_train_between(t) for t in raw_trains],
        )

    entry = TrainSearchEntry(
        source=source, destination=destination, journey_date=body.date, quota=None
    )
    mid = store.put(entry)
    return ManifestResponse(
        manifest_id=mid,
        fetches=[
            build_confirmtkt_descriptor(
                source, destination, body.date, BookingQuota.GENERAL, "search"
            )
        ],
    )


@router.post("/trains-between/process")
async def trains_between_process(body: ProcessRequest, store: ManifestStoreDep):
    entry = store.pop(body.manifest_id)
    if not isinstance(entry, TrainSearchEntry):
        raise HTTPException(404, "Manifest expired or unknown")

    if not body.results:
        raise HTTPException(400, "Missing results")

    r = body.results[0]
    train_list: list[dict] = []
    if r.status == 200 and r.body:
        try:
            payload = json.loads(r.body)
            data = payload.get("data") if isinstance(payload, dict) else None
            train_list = (
                (data or {}).get("trainList", []) if isinstance(data, dict) else []
            )
        except (json.JSONDecodeError, AttributeError):
            pass

    if train_list:
        await SegmentCache.put(
            entry.source,
            entry.destination,
            format_date(entry.journey_date),
            None,
            train_list,
        )

    raw_trains = build_raw_trains_between(train_list)
    return TrainsBetweenResponse(
        source=entry.source,
        destination=entry.destination,
        journey_date=entry.journey_date,
        trains=[to_train_between(t) for t in raw_trains],
    )


# --- Quota Search ---


@router.post("/trains-between/quota/manifest")
async def trains_between_quota_manifest(
    body: QuotaSearchManifestRequest, store: ManifestStoreDep
):
    validate_journey_date(body.date)
    source = body.source.strip().upper()
    destination = body.destination.strip().upper()
    date_str = format_date(body.date)
    fetch_group = body.quota.value

    cached = await SegmentCache.get(source, destination, date_str, fetch_group)
    if cached is not None:
        rows = build_quota_rows(cached)
        return TrainsQuotaAvailabilityResponse(
            source=source,
            destination=destination,
            journey_date=body.date,
            quota=body.quota,
            trains=[
                TrainQuotaClasses(
                    train_number=tn,
                    from_code=fc,
                    departure_time=dpt,
                    classes=[to_class(o) for o in ofs],
                )
                for tn, fc, dpt, ofs in rows
            ],
        )

    entry = TrainSearchEntry(
        source=source, destination=destination, journey_date=body.date, quota=body.quota
    )
    mid = store.put(entry)
    return ManifestResponse(
        manifest_id=mid,
        fetches=[
            build_confirmtkt_descriptor(
                source, destination, body.date, body.quota, "search_quota"
            )
        ],
    )


@router.post("/trains-between/quota/process")
async def trains_between_quota_process(body: ProcessRequest, store: ManifestStoreDep):
    entry = store.pop(body.manifest_id)
    if not isinstance(entry, TrainSearchEntry) or entry.quota is None:
        raise HTTPException(404, "Manifest expired or unknown")

    if not body.results:
        raise HTTPException(400, "Missing results")

    r = body.results[0]
    train_list: list[dict] = []
    if r.status == 200 and r.body:
        try:
            payload = json.loads(r.body)
            data = payload.get("data") if isinstance(payload, dict) else None
            train_list = (
                (data or {}).get("trainList", []) if isinstance(data, dict) else []
            )
        except (json.JSONDecodeError, AttributeError):
            pass

    if train_list:
        await SegmentCache.put(
            entry.source,
            entry.destination,
            format_date(entry.journey_date),
            entry.quota.value,
            train_list,
        )

    rows = build_quota_rows(train_list)
    return TrainsQuotaAvailabilityResponse(
        source=entry.source,
        destination=entry.destination,
        journey_date=entry.journey_date,
        quota=entry.quota,
        trains=[
            TrainQuotaClasses(
                train_number=tn,
                from_code=fc,
                departure_time=dpt,
                classes=[to_class(o) for o in ofs],
            )
            for tn, fc, dpt, ofs in rows
        ],
    )


# --- Stations ---


@router.get("/stations", response_model=list[Station])
def search_stations(
    directory: StationDirectoryDep,
    q: Annotated[
        str, Query(min_length=1, max_length=40, description="Name, city, or code")
    ],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> list[Station]:
    """Autocomplete suggestions from the bundled station directory."""
    return directory.search(q, limit)
