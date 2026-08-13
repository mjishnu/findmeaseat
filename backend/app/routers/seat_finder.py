import json

from fastapi import APIRouter, HTTPException

from app.core.dates import validate_journey_date
from app.core.manifest_store import ManifestCache, SeatFinderEntry
from app.core.pairs import enumerate_pairs
from app.core.parser import parse_availability
from app.core.redis import DeadPairCache, RouteCache, SegmentCache
from app.exceptions import ProviderUnavailableError, TrainNotFoundError
from app.providers.irctc.client import (
    build_availability_descriptor,
    build_confirmtkt_descriptor,
    build_erail_header_descriptor,
    build_erail_route_descriptor,
    format_date,
    parse_erail_header,
    parse_erail_route,
)
from app.providers.prefetched.provider import PreFetchedProvider
from app.routers.common import GzipRoute
from app.schemas import (
    BookingQuota,
    ManifestResponse,
    ProcessRequest,
    RecommendationResponse,
    SeatFinderManifestRequest,
    StationStop,
    TrainRoute,
)
from app.services.recommendations import build_verified_response, rank_candidates

router = APIRouter(route_class=GzipRoute)


@router.post("/manifest", response_model=ManifestResponse | RecommendationResponse)
async def seat_finder_manifest(body: SeatFinderManifestRequest):
    validate_journey_date(body.date)
    source = body.user_source.strip().upper()
    destination = body.user_destination.strip().upper()

    cached_route = await RouteCache.get(body.train_number)
    if cached_route:
        all_pairs = enumerate_pairs(
            cached_route,
            source,
            destination,
            body.partial,
            body.min_coverage_pct,
            body.require_connect,
        )
        pairs = []
        for b, a in all_pairs:
            if not await DeadPairCache.get(body.train_number, b.code, a.code):
                pairs.append((b, a))
        fetch_group = body.quota.fetch_group
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
            partial=body.partial,
            min_coverage_pct=body.min_coverage_pct,
            require_connect=body.require_connect,
        )

        if not fetches:
            provider = PreFetchedProvider(entry, cached_segs)
            ranked_data = await rank_candidates(
                provider,
                cached_route.train_number,
                source,
                destination,
                body.date,
                body.travel_class,
                body.quota,
                body.partial,
                body.min_coverage_pct,
                body.require_connect,
            )
            verify_fetches = []
            for i, cand in enumerate(ranked_data["candidates"]):
                verify_fetches.append(
                    build_availability_descriptor(
                        train_number=cached_route.train_number,
                        travel_class=body.travel_class,
                        quota=body.quota,
                        source=cand["board"]["code"],
                        destination=cand["alight"]["code"],
                        date=body.date,
                        fetch_id=f"verify:{i}",
                    )
                )

            if not verify_fetches:
                return build_verified_response(ranked_data, {})

            entry.phase = "verify"
            entry.verify_candidates = ranked_data["candidates"]
            entry.verify_alternatives = ranked_data["alternatives"]
            entry.verify_context = ranked_data["context"]

            mid = ManifestCache.put(entry)
            return ManifestResponse(manifest_id=mid, fetches=verify_fetches)

        mid = ManifestCache.put(entry)
        return ManifestResponse(manifest_id=mid, fetches=fetches)

    entry = SeatFinderEntry(
        phase="header",
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
    mid = ManifestCache.put(entry)
    return ManifestResponse(
        manifest_id=mid, fetches=[build_erail_header_descriptor(body.train_number)]
    )


@router.post("/process", response_model=ManifestResponse | RecommendationResponse)
async def seat_finder_process(body: ProcessRequest):
    entry = ManifestCache.pop(body.manifest_id)
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
        mid = ManifestCache.put(entry)
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
        all_pairs = enumerate_pairs(
            route,
            entry.user_source,
            entry.user_destination,
            entry.partial,
            entry.min_coverage_pct,
            entry.require_connect,
        )
        pairs = []
        for b, a in all_pairs:
            if not await DeadPairCache.get(entry.train_number, b.code, a.code):
                pairs.append((b, a))
        fetch_group = entry.quota.fetch_group
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
            ranked_data = await rank_candidates(
                provider,
                route.train_number,
                entry.user_source,
                entry.user_destination,
                entry.journey_date,
                entry.travel_class,
                entry.quota,
                entry.partial,
                entry.min_coverage_pct,
                entry.require_connect,
            )
            verify_fetches = []
            for i, cand in enumerate(ranked_data["candidates"]):
                verify_fetches.append(
                    build_availability_descriptor(
                        train_number=route.train_number,
                        travel_class=entry.travel_class,
                        quota=entry.quota,
                        source=cand["board"]["code"],
                        destination=cand["alight"]["code"],
                        date=entry.journey_date,
                        fetch_id=f"verify:{i}",
                    )
                )

            if not verify_fetches:
                return build_verified_response(ranked_data, {})

            entry.phase = "verify"
            entry.verify_candidates = ranked_data["candidates"]
            entry.verify_alternatives = ranked_data["alternatives"]
            entry.verify_context = ranked_data["context"]

            mid = ManifestCache.put(entry)
            return ManifestResponse(manifest_id=mid, fetches=verify_fetches)

        entry.phase = "fetch"
        mid = ManifestCache.put(entry)
        return ManifestResponse(manifest_id=mid, fetches=fetches)

    elif entry.phase == "fetch":
        if entry.fetch_id_to_pair is None or entry.route is None:
            raise HTTPException(500, "Missing pairs or route in entry")

        submitted_ids = [r.fetch_id for r in body.results]
        submitted_set = set(submitted_ids)
        expected_ids = set(entry.fetch_id_to_pair.keys())
        if entry.cached_segments:
            expected_ids -= set(entry.cached_segments.keys())

        if len(submitted_ids) != len(submitted_set):
            raise HTTPException(400, "Duplicate fetch_id")
        if not submitted_set <= expected_ids:
            raise HTTPException(400, "Unknown fetch_id")

        for fetch_id in expected_ids:
            if fetch_id not in submitted_set:
                board, alight = entry.fetch_id_to_pair[fetch_id]
                await DeadPairCache.put(entry.train_number, board.code, alight.code)

        fetch_group = entry.quota.fetch_group
        date_str = format_date(entry.journey_date)
        parsed_segments: dict[str, list[dict]] = {}

        for r in body.results:
            train_list: list[dict] = []
            if r.status == 200 and r.body:
                try:
                    payload = json.loads(r.body)
                    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                        train_list = payload["data"].get("trainList", [])
                except (json.JSONDecodeError, AttributeError):
                    pass
            parsed_segments[r.fetch_id] = train_list
            board, alight = r.fetch_id.split("|")
            if train_list:
                await SegmentCache.put(board, alight, date_str, fetch_group, train_list)

        if entry.cached_segments:
            parsed_segments.update(entry.cached_segments)

        provider = PreFetchedProvider(entry, parsed_segments)
        ranked_data = await rank_candidates(
            provider,
            entry.route.train_number,
            entry.user_source,
            entry.user_destination,
            entry.journey_date,
            entry.travel_class,
            entry.quota,
            entry.partial,
            entry.min_coverage_pct,
            entry.require_connect,
        )
        verify_fetches = []
        for i, cand in enumerate(ranked_data["candidates"]):
            verify_fetches.append(
                build_availability_descriptor(
                    train_number=entry.route.train_number,
                    travel_class=entry.travel_class,
                    quota=entry.quota,
                    source=cand["board"]["code"],
                    destination=cand["alight"]["code"],
                    date=entry.journey_date,
                    fetch_id=f"verify:{i}",
                )
            )
        if not verify_fetches:
            return build_verified_response(ranked_data, {})

        entry.phase = "verify"
        entry.verify_candidates = ranked_data["candidates"]
        entry.verify_alternatives = ranked_data["alternatives"]
        entry.verify_context = ranked_data["context"]

        mid = ManifestCache.put(entry)
        return ManifestResponse(manifest_id=mid, fetches=verify_fetches)

    elif entry.phase == "verify":
        if entry.verify_candidates is None or entry.verify_context is None:
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

            board = cand["board"]["code"]
            alight = cand["alight"]["code"]
            fetch_id = f"{board}|{alight}"

            try:
                payload = json.loads(r.body)
                data = payload.get("data") if isinstance(payload, dict) else None
                if not data:
                    continue

                avl_list = data.get("avlDayList", [])
                fare_info = data.get("fareInfo", {})

                if avl_list and isinstance(avl_list, list):
                    live_day = avl_list[0]
                    live_status = live_day.get("availablityStatus")
                    live_prediction = live_day.get("predictionPercentage")
                    live_fare = fare_info.get("totalFare")
                    if isinstance(live_fare, (int, float)):
                        live_fare = int(round(live_fare))
                    else:
                        live_fare = None

                    live_parsed = (
                        parse_availability(live_status) if live_status else None
                    )

                    if live_parsed:
                        live_overrides[fetch_id] = {
                            "availability": live_parsed,
                            "fare": live_fare,
                        }
                        if live_prediction is not None:
                            try:
                                live_overrides[fetch_id]["prediction_pct"] = int(
                                    live_prediction
                                )
                            except ValueError:
                                pass

                        cached_parsed = cand.get("parsed", {}).get("status")
                        if live_parsed.status != cached_parsed:
                            await SegmentCache.delete(
                                board, alight, date_str, fetch_group
                            )

            except (json.JSONDecodeError, AttributeError):
                pass

        ranked_data = {
            "candidates": entry.verify_candidates,
            "alternatives": entry.verify_alternatives,
            "context": entry.verify_context,
        }

        return build_verified_response(ranked_data, live_overrides)
