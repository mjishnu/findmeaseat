"""Seat finder service — the multi-phase manifest flow for finding optimal booking pairs.

Phases:
  1. manifest: validate → enumerate pairs → check caches → build fetch descriptors
  2. fetch:    parse confirmtkt results → cache segments → rank → build verify descriptors
  3. verify:   parse IRCTC live results → re-rank with overrides → final recommendations
"""

import datetime as dt

from app.domain.dates import validate_journey_date
from app.domain.pairs import enumerate_pairs
from app.exceptions import (
    InvalidManifestError,
    ManifestExpiredError,
    TrainNotFoundError,
)
from app.infrastructure.cache import (
    DeadPairCache,
    RouteCache,
    SeatFinderSegmentCache,
    TrainSearchCache,
)
from app.infrastructure.manifest_store import ManifestCache, SeatFinderEntry
from app.providers.prefetched.client import (
    build_availability_descriptor,
    build_confirmtkt_descriptor,
    format_date,
)
from app.providers.prefetched.parser import (
    extract_json_data,
    parse_verify_result,
)
from app.providers.prefetched.provider import PreFetchedProvider
from app.schemas import (
    BookingQuota,
    FetchResult,
    ManifestResponse,
    RecommendationResponse,
    TravelClass,
)
from app.services.recommendations import build_verified_response, rank_candidates

AVAILABILITY_CACHE_KEYS = (
    "availabilityCache",
    "availabilityCacheTatkal",
    "availabilityCacheForQuota",
)


async def create_manifest(
    train_number: str,
    user_source: str,
    user_destination: str,
    date: dt.date,
    travel_class: TravelClass,
    quota: BookingQuota,
    partial: bool,
    min_coverage_pct: float,
    require_connect: bool,
) -> ManifestResponse | RecommendationResponse:
    """Build fetch descriptors for all uncached station pairs, or short-circuit
    to ranking if everything is already cached."""
    validate_journey_date(date)
    source = user_source.strip().upper()
    destination = user_destination.strip().upper()

    cached_route = await RouteCache.get(train_number)
    if not cached_route:
        raise TrainNotFoundError(train_number)

    all_pairs = enumerate_pairs(
        cached_route,
        source,
        destination,
        partial,
        min_coverage_pct,
        require_connect,
    )
    pairs = []
    for b, a in all_pairs:
        pair_date = cached_route.boarding_date_for(b.code, source, date)
        pair_date_str = format_date(pair_date)
        if not await DeadPairCache.get(train_number, b.code, a.code, pair_date_str):
            pairs.append((b, a))

    fetch_group = quota.fetch_group
    cached_segs: dict[str, dict] = {}
    fetches = []
    fetch_id_to_pair = {}
    for b, a in pairs:
        fid = f"{b.code}|{a.code}"
        fetch_id_to_pair[fid] = (b, a)
        pair_date = cached_route.boarding_date_for(b.code, source, date)
        pair_date_str = format_date(pair_date)

        hit = await SeatFinderSegmentCache.get_field(
            b.code, a.code, pair_date_str, fetch_group, train_number
        )
        if hit is None:
            hit = await TrainSearchCache.get_field(
                b.code, a.code, pair_date_str, fetch_group, train_number
            )
        if hit is not None:
            cached_segs[fid] = hit
        else:
            fetches.append(
                build_confirmtkt_descriptor(b.code, a.code, pair_date, quota, fid)
            )

    entry = SeatFinderEntry(
        phase="fetch",
        route=cached_route,
        pairs=pairs,
        fetch_id_to_pair=fetch_id_to_pair,
        cached_segments=cached_segs,
        train_number=train_number,
        user_source=source,
        user_destination=destination,
        journey_date=date,
        travel_class=travel_class,
        quota=quota,
        partial=partial,
        min_coverage_pct=min_coverage_pct,
        require_connect=require_connect,
    )

    if not fetches:
        return await _rank_and_build_verify_manifest(entry, cached_segs)

    mid = ManifestCache.put(entry)
    return ManifestResponse(manifest_id=mid, fetches=fetches)


async def process_manifest(
    manifest_id: str, results: list[FetchResult]
) -> ManifestResponse | RecommendationResponse:
    """Dispatch to the correct phase handler."""
    entry = ManifestCache.pop(manifest_id)
    if not isinstance(entry, SeatFinderEntry):
        raise ManifestExpiredError()

    if entry.phase == "fetch":
        return await _process_fetch_phase(entry, results)
    elif entry.phase == "verify":
        return await _process_verify_phase(entry, results)

    raise InvalidManifestError(f"Unknown phase: {entry.phase}")


# ── Internal helpers ─────────────────────────────────────────────


async def _rank_and_build_verify_manifest(
    entry: SeatFinderEntry, segments: dict[str, dict]
) -> ManifestResponse | RecommendationResponse:
    """Rank candidates from cached/fetched data, then build verify descriptors."""
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
    verify_fetches = []
    for i, cand in enumerate(ranked_data["candidates"]):
        board_code = cand["board"]["code"]
        cand_date = entry.route.boarding_date_for(
            board_code, entry.user_source, entry.journey_date
        )
        verify_fetches.append(
            build_availability_descriptor(
                train_number=entry.train_number,
                travel_class=entry.travel_class,
                quota=entry.quota,
                source=board_code,
                destination=cand["alight"]["code"],
                date=cand_date,
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


async def _process_fetch_phase(
    entry: SeatFinderEntry, results: list[FetchResult]
) -> ManifestResponse | RecommendationResponse:
    """Parse confirmtkt results, cache segments, mark dead pairs, then rank."""
    if not entry.fetch_id_to_pair:
        raise InvalidManifestError("Missing pairs in entry")

    submitted_ids = [r.fetch_id for r in results]
    submitted_set = set(submitted_ids)
    expected_ids = set(entry.fetch_id_to_pair.keys()) - set(
        entry.cached_segments.keys()
    )

    if len(submitted_ids) != len(submitted_set):
        raise InvalidManifestError("Duplicate fetch_id")
    if not submitted_set <= expected_ids:
        raise InvalidManifestError("Unknown fetch_id")

    fetch_group = entry.quota.fetch_group

    for fetch_id in expected_ids:
        if fetch_id not in submitted_set:
            board, alight = entry.fetch_id_to_pair[fetch_id]
            pair_date = entry.route.boarding_date_for(
                board.code, entry.user_source, entry.journey_date
            )
            await DeadPairCache.put(
                entry.train_number, board.code, alight.code, format_date(pair_date)
            )

    parsed_segments: dict[str, dict] = {}

    for r in results:
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
            board_stop, alight_stop = entry.fetch_id_to_pair[r.fetch_id]
            pair_date = entry.route.boarding_date_for(
                board_stop.code, entry.user_source, entry.journey_date
            )
            stripped_data = {
                k: segment_data[k] for k in AVAILABILITY_CACHE_KEYS if k in segment_data
            }
            await SeatFinderSegmentCache.put_field(
                board_stop.code,
                alight_stop.code,
                format_date(pair_date),
                fetch_group,
                entry.train_number,
                stripped_data,
            )

    parsed_segments.update(entry.cached_segments)
    return await _rank_and_build_verify_manifest(entry, parsed_segments)


async def _process_verify_phase(
    entry: SeatFinderEntry, results: list[FetchResult]
) -> RecommendationResponse:
    """Parse IRCTC live-availability results, apply overrides, re-rank, and return final response."""
    if not entry.verify_candidates or not entry.verify_context:
        raise InvalidManifestError("Missing verify candidates or context in entry")

    fetch_group = entry.quota.fetch_group
    live_overrides = {}

    for r in results:
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
            cand_date = entry.route.boarding_date_for(
                board, entry.user_source, entry.journey_date
            )
            cand_date_str = format_date(cand_date)
            await SeatFinderSegmentCache.delete(
                board, alight, cand_date_str, fetch_group
            )
            await TrainSearchCache.delete(board, alight, cand_date_str, fetch_group)

    ranked_data = {
        "candidates": entry.verify_candidates,
        "alternatives": entry.verify_alternatives,
        "context": entry.verify_context,
    }

    return build_verified_response(ranked_data, live_overrides)
