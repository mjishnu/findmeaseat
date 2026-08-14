import asyncio

from app.core.ranking import confirmation_probability, sort_candidates
from app.exceptions import ProviderUnavailableError
from app.providers.base import RailDataProvider
from app.schemas import (
    AvailabilityStatus,
    BookingQuota,
    Candidate,
    ParsedAvailability,
    Recommendation,
    RecommendationNoteCode,
    StationStop,
    SwitchAlternative,
    TravelClass,
)

MAX_ALTERNATIVES = 3


async def evaluate_pair(
    provider: RailDataProvider,
    board: StationStop,
    alight: StationStop,
    km: dict[str, int],
    user_leg_km: int,
    user_leg_fare: int,
    travel_class: TravelClass,
    quota: BookingQuota = BookingQuota.GENERAL,
) -> Candidate | None:
    parsed = await provider.get_seat_status(
        board.code, alight.code, travel_class, quota
    )
    if parsed.status in (
        AvailabilityStatus.NOT_BOOKABLE,
        AvailabilityStatus.UNKNOWN,
    ):
        return None

    extra_km = max(0, km[alight.code] - km[board.code] - user_leg_km)
    fare = await provider.get_fare(board.code, alight.code, travel_class, quota)
    prediction = await provider.get_seat_prediction(
        board.code, alight.code, travel_class, quota
    )
    extra_fare = fare - user_leg_fare
    probability = confirmation_probability(parsed, prediction)
    return Candidate(
        board=board,
        alight=alight,
        parsed=parsed,
        probability=probability,
        extra_km=extra_km,
        fare=fare,
        extra_fare=extra_fare,
    )


async def evaluate_class(
    provider: RailDataProvider,
    pairs: list[tuple[StationStop, StationStop]],
    source: str,
    destination: str,
    km: dict[str, int],
    user_leg_km: int,
    travel_class: TravelClass,
    quota: BookingQuota = BookingQuota.GENERAL,
) -> tuple[list[Candidate], ParsedAvailability | None, int, int]:
    """Evaluate one (class, quota) cell across every covering pair
    (concurrently) and return (candidates, direct-leg status, skipped count, direct fare).
    """
    user_leg_fare = await provider.get_fare(source, destination, travel_class, quota)
    raw_results = await asyncio.gather(
        *(
            evaluate_pair(
                provider,
                board,
                alight,
                km,
                user_leg_km,
                user_leg_fare,
                travel_class,
                quota,
            )
            for board, alight in pairs
        ),
        return_exceptions=True,
    )
    candidates: list[Candidate] = []
    skipped = 0
    for r in raw_results:
        if isinstance(r, Candidate):
            candidates.append(r)
        elif isinstance(
            r, (type(None), ProviderUnavailableError, asyncio.CancelledError)
        ):
            skipped += 1
        else:
            raise r

    user_leg_parsed = next(
        (
            c.parsed
            for c in candidates
            if c.board.code == source and c.alight.code == destination
        ),
        None,
    )
    return candidates, user_leg_parsed, skipped, user_leg_fare


async def build_better_alternatives(
    provider: RailDataProvider,
    pairs: list[tuple[StationStop, StationStop]],
    source: str,
    destination: str,
    km: dict[str, int],
    user_leg_km: int,
    searched_class: TravelClass,
    searched_quota: BookingQuota,
    searched_best_key: tuple | None,
    searched_best_fare: int,
) -> list[SwitchAlternative]:
    """Build a list of better alternative classes than the current in the same quota (SL in WL10 vs 3A in AVL5)."""
    alternatives: list[SwitchAlternative] = []
    try:
        offered = await provider.get_train_classes(source, destination, searched_quota)
    except ProviderUnavailableError:
        return alternatives
    for tc in offered:
        if tc == searched_class:
            continue  # skip the class the user already searched
        try:
            candidates, _parsed, _skipped, _cell_fare = await evaluate_class(
                provider,
                pairs,
                source,
                destination,
                km,
                user_leg_km,
                tc,
                searched_quota,
            )
            for c in candidates:
                start_code = c.board.code if km[c.board.code] > km[source] else source
                end_code = (
                    c.alight.code
                    if km[c.alight.code] < km[destination]
                    else destination
                )
                c.board_at = start_code
                c.alight_at = end_code
                c.coverage_pct = (km[end_code] - km[start_code]) / user_leg_km

            candidates = [c for c in candidates if c.probability > 0]
        except ProviderUnavailableError:
            continue

        if not candidates:
            continue

        _, best, best_key = sort_candidates(candidates, _cell_fare, user_leg_km)
        if (
            searched_best_key is not None
            and best_key is not None
            and best_key <= searched_best_key
        ):
            continue  # only better than the searched class's best are kept others skipped
        fare_delta = best.fare - searched_best_fare
        alternatives.append(
            SwitchAlternative(
                travel_class=tc,
                quota=searched_quota,
                availability=best.parsed,
                probability=round(best.probability, 3),
                fare=best.fare,
                fare_delta=fare_delta,
            )
        )
    alternatives.sort(key=lambda a: -a.probability)
    return alternatives[:MAX_ALTERNATIVES]


def build_recommendation(
    rank: int,
    cand: Candidate,
    source: str,
    destination: str,
    quota: BookingQuota = BookingQuota.GENERAL,
) -> Recommendation:
    notes: list[RecommendationNoteCode] = []

    QUOTA_NOTE_CODE = {
        BookingQuota.TATKAL: RecommendationNoteCode.QUOTA_TATKAL,
        BookingQuota.LADIES: RecommendationNoteCode.QUOTA_LADIES,
        BookingQuota.SENIOR: RecommendationNoteCode.QUOTA_SENIOR,
    }

    if note := QUOTA_NOTE_CODE.get(quota):
        notes.append(note)

    if cand.extra_fare > 0:
        notes.append(RecommendationNoteCode.EXTRA_FARE)
    if cand.probability < 0:
        notes.append(RecommendationNoteCode.MISSING_PREDICTION)
    if cand.board.code != source:
        notes.append(RecommendationNoteCode.BOARDING_CHANGE)
    if cand.alight.code != destination:
        notes.append(RecommendationNoteCode.ALIGHT_CHANGE)
    if cand.coverage_pct < 1.0:
        notes.append(RecommendationNoteCode.PARTIAL_COVERAGE)

    # For full-coverage (covering) pairs, the user rides their full journey.
    # For partial pairs, they ride the overlap: max(board, source) → min(alight, dest).
    board_at = cand.board_at if cand.board_at else source
    alight_at = cand.alight_at if cand.alight_at else destination

    return Recommendation(
        rank=rank,
        book_from=cand.board.code,
        book_to=cand.alight.code,
        board_at=board_at,
        alight_at=alight_at,
        availability=cand.parsed,
        probability=round(cand.probability, 3),
        extra_km=cand.extra_km,
        fare=cand.fare,
        extra_fare=cand.extra_fare,
        coverage_pct=round(cand.coverage_pct, 3),
        notes=notes,
    )
