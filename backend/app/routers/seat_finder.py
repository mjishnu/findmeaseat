from fastapi import APIRouter, HTTPException

from app.core.dates import validate_journey_date
from app.core.manifest_store import ManifestCache, SeatFinderEntry
from app.core.pairs import enumerate_pairs
from app.core.parser import extract_json_data, parse_verify_result
from app.core.redis import DeadPairCache, FullSearchCache, RouteCache, SegmentCache
from app.exceptions import TrainNotFoundError
from app.providers.irctc.client import (
    build_availability_descriptor,
    build_confirmtkt_descriptor,
    format_date,
)
from app.providers.prefetched.provider import PreFetchedProvider
from app.routers.common import GzipRoute
from app.schemas import (
    ManifestResponse,
    ProcessRequest,
    RecommendationResponse,
    SeatFinderManifestRequest,
)
from app.services.recommendations import build_verified_response, rank_candidates

router = APIRouter(route_class=GzipRoute)


async def _rank_and_build_verify_manifest(
    entry: SeatFinderEntry, segments: dict[str, dict]
) -> ManifestResponse | RecommendationResponse:
    provider = PreFetchedProvider(entry, segments)
    ranked_data = await rank_candidates(
        provider,
        entry.train_number,
        entry.user_source,
        entry.user_destination,
        entry.journey_date,
        entry.travel_class,
        entry.quota,
        entry.partial,
        entry.min_coverage_pct,
        entry.require_connect,
    )
    verify_fetches = [
        build_availability_descriptor(
            train_number=entry.train_number,
            travel_class=entry.travel_class,
            quota=entry.quota,
            source=cand["board"]["code"],
            destination=cand["alight"]["code"],
            date=entry.journey_date,
            fetch_id=f"verify:{i}",
        )
        for i, cand in enumerate(ranked_data["candidates"])
    ]

    if not verify_fetches:
        return build_verified_response(ranked_data, {})

    entry.phase = "verify"
    entry.verify_candidates = ranked_data["candidates"]
    entry.verify_alternatives = ranked_data["alternatives"]
    entry.verify_context = ranked_data["context"]

    mid = ManifestCache.put(entry)
    return ManifestResponse(manifest_id=mid, fetches=verify_fetches)


@router.post("/manifest", response_model=ManifestResponse | RecommendationResponse)
async def seat_finder_manifest(body: SeatFinderManifestRequest):
    validate_journey_date(body.date)
    source = body.user_source.strip().upper()
    destination = body.user_destination.strip().upper()

    cached_route = await RouteCache.get(body.train_number)
    if not cached_route:
        raise TrainNotFoundError(body.train_number)

    all_pairs = enumerate_pairs(
        cached_route,
        source,
        destination,
        body.partial,
        body.min_coverage_pct,
        body.require_connect,
    )
    date_str = format_date(body.date)
    pairs = []
    for b, a in all_pairs:
        if not await DeadPairCache.get(body.train_number, b.code, a.code, date_str):
            pairs.append((b, a))
    fetch_group = body.quota.fetch_group
    cached_segs: dict[str, dict] = {}
    fetches = []
    fetch_id_to_pair = {}
    for b, a in pairs:
        fid = f"{b.code}|{a.code}"
        fetch_id_to_pair[fid] = (b, a)
        hit = await SegmentCache.get_field(
            b.code, a.code, date_str, fetch_group, body.train_number
        )
        if hit is not None:
            cached_segs[fid] = hit
        else:
            fetches.append(
                build_confirmtkt_descriptor(b.code, a.code, body.date, body.quota, fid)
            )

    entry = SeatFinderEntry(
        phase="fetch",
        route=cached_route,
        pairs=pairs,
        fetch_id_to_pair=fetch_id_to_pair,
        cached_segments=cached_segs,
        train_number=body.train_number,
        user_source=source,
        user_destination=destination,
        journey_date=body.date,
        travel_class=body.travel_class,
        quota=body.quota,
        partial=body.partial,
        min_coverage_pct=body.min_coverage_pct,
        require_connect=body.require_connect,
    )

    if not fetches:
        return await _rank_and_build_verify_manifest(entry, cached_segs)

    mid = ManifestCache.put(entry)
    return ManifestResponse(manifest_id=mid, fetches=fetches)


async def _process_fetch_phase(
    entry: SeatFinderEntry, body: ProcessRequest
) -> ManifestResponse | RecommendationResponse:
    if not entry.fetch_id_to_pair or entry.route is None:
        raise HTTPException(500, "Missing pairs or route in entry")

    submitted_ids = [r.fetch_id for r in body.results]
    submitted_set = set(submitted_ids)
    expected_ids = set(entry.fetch_id_to_pair.keys()) - set(
        entry.cached_segments.keys()
    )

    if len(submitted_ids) != len(submitted_set):
        raise HTTPException(400, "Duplicate fetch_id")
    if not submitted_set <= expected_ids:
        raise HTTPException(400, "Unknown fetch_id")

    fetch_group = entry.quota.fetch_group
    date_str = format_date(entry.journey_date)

    for fetch_id in expected_ids:
        if fetch_id not in submitted_set:
            board, alight = entry.fetch_id_to_pair[fetch_id]
            await DeadPairCache.put(entry.train_number, board.code, alight.code, date_str)

    parsed_segments: dict[str, dict] = {}

    for r in body.results:
        if r.status != 200 or not r.body:
            continue

        data = extract_json_data(r.body)
        if not data:
            continue

        # Frontend prefilters to the target train (1 element in trainList)
        train_list = data.get("trainList", [])
        if train_list and isinstance(train_list[0], dict):
            segment_data = train_list[0]
            parsed_segments[r.fetch_id] = segment_data
            board, alight = r.fetch_id.split("|")
            await SegmentCache.put_field(
                board,
                alight,
                date_str,
                fetch_group,
                entry.train_number,
                segment_data,
            )

    parsed_segments.update(entry.cached_segments)
    return await _rank_and_build_verify_manifest(entry, parsed_segments)


async def _process_verify_phase(
    entry: SeatFinderEntry, body: ProcessRequest
) -> RecommendationResponse:
    if not entry.verify_candidates or not entry.verify_context:
        raise HTTPException(500, "Missing verify candidates or context in entry")

    fetch_group = entry.quota.fetch_group
    date_str = format_date(entry.journey_date)
    live_overrides = {}

    for r in body.results:
        if r.status != 200 or not r.body:
            continue

        try:
            idx = int(r.fetch_id.split(":")[1])
            cand = entry.verify_candidates[idx]
        except (IndexError, ValueError):
            continue

        override = parse_verify_result(r.body)
        if not override:
            continue

        board = cand["board"]["code"]
        alight = cand["alight"]["code"]
        fetch_id = f"{board}|{alight}"

        live_overrides[fetch_id] = override

        cached_parsed = cand.get("parsed", {})
        if override["availability"].raw != cached_parsed.get("raw"):
            await SegmentCache.delete(board, alight, date_str, fetch_group)
            await FullSearchCache.delete(board, alight, date_str, fetch_group)

    ranked_data = {
        "candidates": entry.verify_candidates,
        "alternatives": entry.verify_alternatives,
        "context": entry.verify_context,
    }

    return build_verified_response(ranked_data, live_overrides)


@router.post("/process", response_model=ManifestResponse | RecommendationResponse)
async def seat_finder_process(body: ProcessRequest):
    entry = ManifestCache.pop(body.manifest_id)
    if not isinstance(entry, SeatFinderEntry):
        raise HTTPException(404, "Manifest expired or unknown")

    if entry.phase == "fetch":
        return await _process_fetch_phase(entry, body)
    elif entry.phase == "verify":
        return await _process_verify_phase(entry, body)

    raise HTTPException(500, f"Unknown phase: {entry.phase}")
