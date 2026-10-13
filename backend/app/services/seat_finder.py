"""Seat finder service — the multi-phase manifest flow for finding optimal booking pairs.

Phases:
  1. manifest: validate → enumerate pairs → check caches → build fetch descriptors
  2. fetch:    parse confirmtkt results → cache segments → check boarding dates
  3. recheck:  only when a boarding date was wrong → refetch those boards on the right date
  4. fill:     live-check pairs whose availability confirmtkt's search left empty
  5. verify:   parse IRCTC live results → re-rank with overrides → final recommendations

Boarding dates start from the route's day offsets (erail), which go stale when a
timetable changes. confirmtkt's own departure times and durations are current, so
each board's date is checked against the user's station: both reach the same alight
station at the same instant, which pins down how many days apart they depart.
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
    BoardDayCache,
    RouteCache,
    SeatFinderSegmentCache,
    TrainSearchCache,
)
from app.infrastructure.manifest_store import ManifestCache, SeatFinderEntry
from app.providers.prefetched.client import (
    build_availability_descriptor,
    build_confirmtkt_descriptor,
    format_date,
    has_class_availability,
    quota_cache_key,
    to_int,
)
from app.providers.prefetched.parser import (
    extract_json_data,
    parse_verify_result,
)
from app.providers.prefetched.provider import PreFetchedProvider
from app.schemas import (
    BookingQuota,
    FetchDescriptor,
    FetchResult,
    ManifestResponse,
    RecommendationResponse,
    TravelClass,
)
from app.services.recommendations import build_verified_response, rank_candidates

SEGMENT_CACHE_KEYS = (
    "availabilityCache",
    "availabilityCacheTatkal",
    "availabilityCacheForQuota",
    # identify the pair and timing the segment belongs to
    "fromStnCode",
    "toStnCode",
    "departureTime",
    "duration",
)

ONE_DAY = dt.timedelta(days=1)
MINUTES_PER_DAY = 24 * 60
# confirmtkt durations are schedule-exact; allow a little slack for rounding quirks
TIMING_TOLERANCE_MIN = 60
# Most pairs to live-check per search when confirmtkt's search left them empty
MAX_LIVE_FILLS = 40

PairOnDate = tuple[str, str, dt.date]


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
    source = user_source.strip().upper()
    destination = user_destination.strip().upper()

    cached_route = await RouteCache.get(train_number)
    if not cached_route:
        raise TrainNotFoundError(train_number)
    validate_journey_date(date, cached_route.get_day_offset(source))

    pairs = enumerate_pairs(
        cached_route,
        source,
        destination,
        partial,
        min_coverage_pct,
        require_connect,
    )

    board_dates = {}
    for b, _ in pairs:
        if b.code in board_dates:
            continue
        days = await BoardDayCache.get(train_number, b.code, source)
        board_dates[b.code] = (
            date - dt.timedelta(days=days)
            if days is not None
            else cached_route.boarding_date_for(b.code, source, date)
        )

    entry = SeatFinderEntry(
        phase="fetch",
        route=cached_route,
        pairs=pairs,
        board_dates=board_dates,
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
    wanted = [(b.code, a.code, entry.board_dates[b.code]) for b, a in pairs]
    return await _advance(entry, await _collect(entry, wanted))


async def process_manifest(
    manifest_id: str, results: list[FetchResult]
) -> ManifestResponse | RecommendationResponse:
    """Dispatch to the correct phase handler."""
    entry = ManifestCache.pop(manifest_id)
    if not isinstance(entry, SeatFinderEntry):
        raise ManifestExpiredError()

    if entry.phase in ("fetch", "recheck"):
        await _ingest(entry, results)
        return await _advance(entry, [])
    elif entry.phase == "fill":
        await _ingest_live(entry, results)
        return await _advance(entry, [])
    elif entry.phase == "verify":
        return await _process_verify_phase(entry, results)

    raise InvalidManifestError(f"Unknown phase: {entry.phase}")


# ── Internal helpers ─────────────────────────────────────────────


def _is_usable(
    segment: dict | None,
    board: str,
    alight: str,
    travel_class: TravelClass,
    quota: BookingQuota,
) -> bool:
    """A cached segment only counts as a hit if it is for this exact pair (not a
    nearby station confirmtkt substituted) and answers this class/quota;
    confirmtkt's not-yet-computed placeholders are refetched."""
    return (
        segment is not None
        and segment.get("fromStnCode") == board
        and segment.get("toStnCode") == alight
        and has_class_availability(segment, travel_class.value, quota)
    )


async def _collect(
    entry: SeatFinderEntry, wanted: list[PairOnDate]
) -> list[FetchDescriptor]:
    """Fill `entry.found` from cache; return fetches for the rest."""
    fetch_group = entry.quota.fetch_group
    fetches = []
    for board, alight, date in wanted:
        if (board, alight, date) in entry.found:
            continue
        date_str = format_date(date)

        hit = await SeatFinderSegmentCache.get_field(
            board, alight, date_str, fetch_group, entry.train_number
        )
        if not _is_usable(hit, board, alight, entry.travel_class, entry.quota):
            hit = await TrainSearchCache.get_field(
                board, alight, date_str, fetch_group, entry.train_number
            )
        if _is_usable(hit, board, alight, entry.travel_class, entry.quota):
            entry.found[(board, alight, date)] = hit
            continue

        # The frontend labels its progress bar from the "recheck:" prefix
        prefix = "recheck:" if entry.phase == "recheck" else ""
        fid = f"{prefix}{board}|{alight}|{date_str}"
        if fid not in entry.pending:
            entry.pending[fid] = (board, alight, date)
            fetches.append(
                build_confirmtkt_descriptor(board, alight, date, entry.quota, fid)
            )
    return fetches


def _check_submitted(entry: SeatFinderEntry, results: list[FetchResult]) -> None:
    submitted_ids = [r.fetch_id for r in results]
    if len(submitted_ids) != len(set(submitted_ids)):
        raise InvalidManifestError("Duplicate fetch_id")
    if not set(submitted_ids) <= entry.pending.keys():
        raise InvalidManifestError("Unknown fetch_id")


async def _cache_segment(
    entry: SeatFinderEntry, board: str, alight: str, date: dt.date, train: dict
) -> None:
    await SeatFinderSegmentCache.put_field(
        board,
        alight,
        format_date(date),
        entry.quota.fetch_group,
        entry.train_number,
        {k: train[k] for k in SEGMENT_CACHE_KEYS if k in train},
    )


async def _ingest(entry: SeatFinderEntry, results: list[FetchResult]) -> None:
    """Parse confirmtkt results into `entry.found` / `entry.not_listed` and cache them."""
    _check_submitted(entry, results)

    for r in results:
        board, alight, date = entry.pending[r.fetch_id]
        if r.status != 200 or not r.body:
            continue

        data = extract_json_data(r.body)
        train_list = data.get("trainList") if data else None
        if not isinstance(train_list, list):
            continue

        # Frontend prefilters to the target train; confirmtkt may still hand it back
        # for a nearby station instead of the one asked, which isn't this pair.
        train = next(
            (
                t
                for t in train_list
                if isinstance(t, dict)
                and t.get("fromStnCode") == board
                and t.get("toStnCode") == alight
            ),
            None,
        )
        if train is None:
            entry.not_listed.add((board, alight, date))
            continue

        entry.found[(board, alight, date)] = train
        await _cache_segment(entry, board, alight, date, train)
    entry.pending.clear()


def _live_fill_fetches(entry: SeatFinderEntry) -> list[FetchDescriptor]:
    """Live checks for listed pairs whose searched class confirmtkt's search left
    empty. confirmtkt only computes those once someone checks the pair live, so
    refetching the search never fills them; a live check does, for this search and
    (once cached) the next. Nearest pairs first, at most MAX_LIVE_FILLS."""
    empty = []
    for b, a in entry.pairs:
        date = entry.board_dates[b.code]
        train = entry.found.get((b.code, a.code, date))
        if train is not None and not has_class_availability(
            train, entry.travel_class.value, entry.quota
        ):
            empty.append((a.distance_km - b.distance_km, b.code, a.code, date))

    fetches = []
    for _, board, alight, date in sorted(empty)[:MAX_LIVE_FILLS]:
        fid = f"fill:{board}|{alight}|{format_date(date)}"
        entry.pending[fid] = (board, alight, date)
        fetches.append(
            build_availability_descriptor(
                train_number=entry.train_number,
                travel_class=entry.travel_class,
                quota=entry.quota,
                source=board,
                destination=alight,
                date=date,
                fetch_id=fid,
            )
        )
    return fetches


def _with_live(entry: SeatFinderEntry, train: dict, live: dict) -> dict:
    """Copy of a confirmtkt train dict with the searched class/quota set to a live answer."""
    key = quota_cache_key(entry.quota)
    quota_cache = dict(train.get(key) or {})
    previous = quota_cache.get(entry.travel_class.value) or {}
    quota_cache[entry.travel_class.value] = {
        # the parser's labels ("AVL 1", "WL 10", "RAC 5", "REGRET...") parse back
        # to the same status
        "availability": live["availability"].raw,
        "availabilityDisplayName": "",
        "fare": live["fare"] if live.get("fare") is not None else previous.get("fare"),
        "predictionPercentage": live.get("prediction_pct", -1),
    }
    return {**train, key: quota_cache}


async def _apply_live(
    entry: SeatFinderEntry, board: str, alight: str, date: dt.date, live: dict
) -> None:
    """Record a live answer in this search, our pair cache, and the trains-between
    cache (that train only, keeping its expiry), so the next search reuses it."""
    if (board, alight, date) in entry.found:
        train = _with_live(entry, entry.found[(board, alight, date)], live)
        entry.found[(board, alight, date)] = train
        await _cache_segment(entry, board, alight, date, train)

    parts = (board, alight, format_date(date), entry.quota.fetch_group)
    listed = await TrainSearchCache.get_field(*parts, entry.train_number)
    if listed is not None:
        await TrainSearchCache.update_field(
            *parts, entry.train_number, _with_live(entry, listed, live)
        )


async def _ingest_live(entry: SeatFinderEntry, results: list[FetchResult]) -> None:
    """Record the fill round's live answers."""
    _check_submitted(entry, results)
    for r in results:
        board, alight, date = entry.pending[r.fetch_id]
        live = parse_verify_result(r.body) if r.status == 200 and r.body else None
        if live is None:
            continue
        await _apply_live(entry, board, alight, date, live)
        entry.live_checked.add(f"{board}|{alight}")
    entry.pending.clear()


async def _advance(
    entry: SeatFinderEntry, fetches: list[FetchDescriptor]
) -> ManifestResponse | RecommendationResponse:
    """Send this round's fetches, or move on: date check → recheck → fill → verify."""
    if fetches:
        mid = ManifestCache.put(entry)
        return ManifestResponse(manifest_id=mid, fetches=fetches)

    if entry.phase == "fetch":
        entry.recheck_dates = _wrong_board_dates(entry)
        if entry.recheck_dates:
            entry.phase = "recheck"
            wanted = [
                (b.code, a.code, date)
                for b, a in entry.pairs
                for date in entry.recheck_dates.get(b.code, ())
            ]
            return await _advance(entry, await _collect(entry, wanted))
    elif entry.phase == "recheck":
        for board, date in _settle_board_dates(entry).items():
            await BoardDayCache.put(
                entry.train_number,
                board,
                entry.user_source,
                (entry.journey_date - date).days,
            )

    if entry.phase in ("fetch", "recheck"):
        entry.phase = "fill"
        return await _advance(entry, _live_fill_fetches(entry))

    return await _rank_and_build_verify_manifest(entry)


def _arrival_minutes(train: dict) -> int | None:
    """Minutes from midnight of the boarding day to arrival at the alight station."""
    try:
        hours, minutes = str(train.get("departureTime")).split(":")
        departure = int(hours) * 60 + int(minutes)
    except ValueError:
        return None
    duration = to_int(train.get("duration"))
    return departure + duration if duration > 0 else None


def _arrivals(entry: SeatFinderEntry, board: str, date: dt.date) -> dict[str, int]:
    """Alight station -> arrival minutes, for this board's pairs fetched on `date`."""
    out = {}
    for (b, a, d), train in entry.found.items():
        if b == board and d == date and (m := _arrival_minutes(train)) is not None:
            out[a] = m
    return out


def _board_date_from_timings(
    entry: SeatFinderEntry, board: str, date: dt.date, anchor: dict[str, int]
) -> dt.date | None:
    """The date the user's train departs `board`, from confirmtkt timings: the board
    and the user's own station reach a shared alight station at the same instant,
    so their arrival-minute difference is a whole number of days."""
    arrivals = _arrivals(entry, board, date)
    days = set()
    for alight in arrivals.keys() & anchor.keys():
        diff = arrivals[alight] - anchor[alight]
        whole = round(diff / MINUTES_PER_DAY)
        if abs(diff - whole * MINUTES_PER_DAY) > TIMING_TOLERANCE_MIN:
            return None
        days.add(whole)
    if len(days) != 1:
        return None
    return entry.journey_date - dt.timedelta(days=days.pop())


def _wrong_board_dates(entry: SeatFinderEntry) -> dict[str, list[dt.date]]:
    """Boards queried on the wrong date, with the dates to try instead: a single
    date is pinned by timings; several are candidates to probe."""
    anchor = _arrivals(entry, entry.user_source, entry.journey_date)
    if not anchor:
        # Train not seen from the user's own station on their date: nothing to
        # measure against (wrong travel date, or the provider failed).
        return {}

    out = {}
    for board, queried in entry.board_dates.items():
        if board == entry.user_source:
            continue
        actual = _board_date_from_timings(entry, board, queried, anchor)
        if actual is not None:
            if actual != queried:
                out[board] = [actual]
        elif not _arrivals(entry, board, queried) and any(
            b == board and d == queried for b, _, d in entry.not_listed
        ):
            # Cleanly not listed that day: a non-daily train whose date is off.
            # Stale route offsets are off by one; try around the route's date
            # (which also covers a remembered offset that has since gone stale).
            # Failed fetches are left alone; a retry can't fix those.
            route_date = entry.route.boarding_date_for(
                board, entry.user_source, entry.journey_date
            )
            out[board] = sorted(
                {route_date - ONE_DAY, route_date, route_date + ONE_DAY} - {queried}
            )
    return out


def _settle_board_dates(entry: SeatFinderEntry) -> dict[str, dt.date]:
    """After the recheck round, adopt the date each rechecked board really runs on.
    Returns the boards whose date is proven by timings (safe to remember)."""
    anchor = _arrivals(entry, entry.user_source, entry.journey_date)
    proven = {}
    for board, dates in entry.recheck_dates.items():
        if len(dates) == 1:
            # Pinned by timings; even if the refetch failed, the old date's data
            # belongs to a different run and must not be used.
            entry.board_dates[board] = proven[board] = dates[0]
            continue
        timed = {
            d: _board_date_from_timings(entry, board, d, anchor)
            for d in dates
            if _arrivals(entry, board, d)
        }
        confirmed = [d for d, actual in timed.items() if actual == d]
        if confirmed:
            entry.board_dates[board] = proven[board] = confirmed[0]
        elif len(timed) == 1 and None in timed.values():
            # Listed on just one candidate and timings can't say otherwise.
            # If timings point elsewhere, that listing is another day's run: skip.
            entry.board_dates[board] = next(iter(timed))
    return proven


def _segments(entry: SeatFinderEntry) -> dict[str, dict]:
    """'B|A' -> train dict on each board's settled date, for ranking."""
    out = {}
    for b, a in entry.pairs:
        train = entry.found.get((b.code, a.code, entry.board_dates[b.code]))
        if train is not None:
            out[f"{b.code}|{a.code}"] = train
    return out


async def _rank_and_build_verify_manifest(
    entry: SeatFinderEntry,
) -> ManifestResponse | RecommendationResponse:
    """Rank candidates from cached/fetched data, then build verify descriptors."""
    segments = _segments(entry)
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
    # Pairs with no answer for this class (not listed, failed, or confirmtkt hasn't
    # computed it yet) are "no data", not "unavailable"
    ranked_data["context"]["pairs_no_data"] = sum(
        1
        for b, a in entry.pairs
        if not has_class_availability(
            segments.get(f"{b.code}|{a.code}", {}),
            entry.travel_class.value,
            entry.quota,
        )
    )
    verify_fetches = []
    for i, cand in enumerate(ranked_data["candidates"]):
        board_code = cand["board"]["code"]
        if f"{board_code}|{cand['alight']['code']}" in entry.live_checked:
            continue  # checked live moments ago in the fill round
        verify_fetches.append(
            build_availability_descriptor(
                train_number=entry.train_number,
                travel_class=entry.travel_class,
                quota=entry.quota,
                source=board_code,
                destination=cand["alight"]["code"],
                date=entry.board_dates[board_code],
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


async def _process_verify_phase(
    entry: SeatFinderEntry, results: list[FetchResult]
) -> RecommendationResponse:
    """Parse IRCTC live-availability results, apply overrides, re-rank, and return final response."""
    if not entry.verify_candidates or not entry.verify_context:
        raise InvalidManifestError("Missing verify candidates or context in entry")

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
        # Keep the fresher live answer rather than deleting the cache: confirmtkt's
        # search API lags behind it, so a refetch would only bring back stale data
        await _apply_live(entry, board, alight, entry.board_dates[board], override)

    ranked_data = {
        "candidates": entry.verify_candidates,
        "alternatives": entry.verify_alternatives,
        "context": entry.verify_context,
    }

    return build_verified_response(ranked_data, live_overrides)
