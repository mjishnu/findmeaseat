"""Orchestrates a search: enumerate covering pairs, fetch + parse each
status concurrently, rank, and build the top-3 response with human-readable
actions."""
import asyncio
import datetime as dt
import math
from dataclasses import dataclass

from app.core.dates import booking_day_today, validate_journey_date
from app.core.pairs import enumerate_covering_pairs
from app.core.parser import parse_availability
from app.core.ranking import confirmation_probability, option_score
from app.exceptions import (
    ProviderUnavailableError,
    TrainNotFoundError,
)
from app.providers.base import RailDataProvider
from app.schemas import (
    AvailabilityStatus,
    BookingQuota,
    ParsedAvailability,
    Recommendation,
    RecommendationResponse,
    StationStop,
    SwitchAlternative,
    TravelClass,
    UserLeg,
)

MAX_RECOMMENDATIONS = 3
MAX_ALTERNATIVES = 3  # the (class × quota) grid is ~16 cells; keep the banner tidy
# booking_day_today / ADVANCE_RESERVATION_DAYS / BOOKING_TZ / validate_journey_date
# are imported from app.core.dates (shared with train search) and re-exported here
# for callers/tests that import them from this module.

# Per-quota note + action suffix for non-General bookings. General needs neither.
_QUOTA_NOTE = {
    BookingQuota.TATKAL: "Book under the Tatkal quota on IRCTC — it opens ~1 day "
                         "before travel and carries a higher fare than General.",
    BookingQuota.LADIES: "Book under the Ladies quota on IRCTC — reserved for women "
                         "travellers (and a child under 12 travelling with them).",
    BookingQuota.SENIOR: "Book under the Senior Citizen quota on IRCTC — for eligible "
                         "senior citizens; carry valid age proof.",
}
_QUOTA_ACTION_SUFFIX = {
    BookingQuota.TATKAL: " in Tatkal quota",
    BookingQuota.LADIES: " in Ladies quota",
    BookingQuota.SENIOR: " in Senior Citizen quota",
}


@dataclass
class _Candidate:
    board: StationStop
    alight: StationStop
    parsed: ParsedAvailability
    probability: float
    score: float
    booked_km: int
    extra_km: int
    fare: int | None
    extra_fare: int | None


@dataclass
class _PairResult:
    board: StationStop
    alight: StationStop
    parsed: ParsedAvailability
    candidate: _Candidate | None


class RecommendationService:
    def __init__(self, provider: RailDataProvider) -> None:
        self._provider = provider

    async def find_optimal_route(
        self,
        train_number: str,
        user_source: str,
        user_destination: str,
        journey_date: dt.date,
        travel_class: TravelClass = TravelClass.SL,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> RecommendationResponse:
        source = user_source.strip().upper()
        destination = user_destination.strip().upper()
        validate_journey_date(journey_date)

        route = await self._provider.get_route(train_number)
        if route is None:
            raise TrainNotFoundError(train_number)

        pairs = enumerate_covering_pairs(route, source, destination)
        km = {stop.code: stop.distance_km for stop in route.stations}
        user_leg_km = km[destination] - km[source]
        candidates, user_leg_parsed, pairs_skipped, user_leg_fare = await self._evaluate_class(
            train_number, pairs, source, destination, km, user_leg_km, journey_date,
            travel_class, quota,
        )

        # Best score first; ties: higher raw probability, cheaper, shorter.
        # Unknown fare sorts last on the cost tie-breaker (never "cheapest").
        candidates.sort(
            key=lambda c: (
                -c.score,
                -c.probability,
                c.extra_fare if c.extra_fare is not None else math.inf,
                c.extra_km,
            )
        )

        recommendations = [
            self._build_recommendation(rank, cand, source, destination, quota)
            for rank, cand in enumerate(candidates[:MAX_RECOMMENDATIONS], start=1)
        ]
        # Baseline for the switch banner = the BEST chance achievable in the
        # searched (class, quota) cell (across pairs), not just the direct leg.
        chosen_best = max(candidates, key=lambda c: c.probability, default=None)
        chosen_best_prob = chosen_best.probability if chosen_best else 0.0
        chosen_best_fare = chosen_best.fare if chosen_best else user_leg_fare
        alternatives = await self._build_alternatives(
            train_number, pairs, source, destination, km, user_leg_km, journey_date,
            travel_class, quota, chosen_best_prob, chosen_best_fare,
        )
        return RecommendationResponse(
            train_number=route.train_number,
            train_name=route.train_name,
            journey_date=journey_date,
            travel_class=travel_class,
            quota=quota,
            user_leg=UserLeg(
                source=source,
                destination=destination,
                distance_km=user_leg_km,
                fare=user_leg_fare,
                availability=user_leg_parsed,
            ),
            pairs_evaluated=len(pairs),
            pairs_skipped=pairs_skipped,
            recommendations=recommendations,
            alternatives=alternatives,
        )

    async def _evaluate_class(
        self,
        train_number: str,
        pairs: list[tuple[StationStop, StationStop]],
        source: str,
        destination: str,
        km: dict[str, int],
        user_leg_km: int,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> tuple[list[_Candidate], ParsedAvailability | None, int, int | None]:
        """Evaluate one (class, quota) cell across every covering pair
        (concurrently) and return (candidates, direct-leg status, skipped count,
        direct fare).

        Used both for the searched cell and, with cached pair responses, for each
        alternative (class × quota) cell — issuing no extra upstream requests beyond
        the searched cell's for a GN/TQ search (an LD/SS search adds one GN/TQ bundle).
        Degrades gracefully on per-pair upstream failures.
        """
        user_leg_fare = await self._provider.get_fare(
            train_number, source, destination, journey_date, travel_class, quota
        )
        raw_results = await asyncio.gather(
            *(
                self._evaluate_pair(
                    train_number, board, alight, km, user_leg_km, user_leg_fare,
                    journey_date, travel_class, quota,
                )
                for board, alight in pairs
            ),
            return_exceptions=True,
        )
        results: list[_PairResult] = []
        skipped = 0
        for r in raw_results:
            if isinstance(r, _PairResult):
                results.append(r)
            elif isinstance(r, (ProviderUnavailableError, asyncio.CancelledError)):
                skipped += 1
            else:
                raise r  # a genuine bug (or fatal BaseException) — never mask it

        candidates = [r.candidate for r in results if r.candidate is not None]
        user_leg_parsed = next(
            (r.parsed for r in results if r.board.code == source and r.alight.code == destination),
            None,
        )
        return candidates, user_leg_parsed, skipped, user_leg_fare

    async def _build_alternatives(
        self,
        train_number: str,
        pairs: list[tuple[StationStop, StationStop]],
        source: str,
        destination: str,
        km: dict[str, int],
        user_leg_km: int,
        journey_date: dt.date,
        searched_class: TravelClass,
        searched_quota: BookingQuota,
        searched_best_prob: float,
        searched_best_fare: int | None,
    ) -> list[SwitchAlternative]:
        """Across the full (class × quota) grid — both quotas, every class each
        offers — the BEST achievable option per cell across covering pairs (not
        just the direct leg). Reuses the searched cell's cached GN/TQ pair responses
        (an LD/SS search adds one bundled GN/TQ fetch here — still single-flighted).
        A bonus signal — never fatal — so an upstream hiccup degrades to []. Keeps
        only strictly-better cells, sorted by probability, capped at the top few so
        the banner stays tidy."""
        alternatives: list[SwitchAlternative] = []
        for q in (BookingQuota.GENERAL, BookingQuota.TATKAL):
            try:
                offered = await self._provider.get_class_options(
                    train_number, source, destination, journey_date, q
                )
            except ProviderUnavailableError:
                continue
            for code, _raw, _fare in offered:
                try:
                    tc = TravelClass(code)
                except ValueError:
                    continue  # a class our enum doesn't model
                if tc == searched_class and q == searched_quota:
                    continue  # skip the cell the user already searched
                try:
                    candidates, _parsed, _skipped, _cell_fare = await self._evaluate_class(
                        train_number, pairs, source, destination, km, user_leg_km,
                        journey_date, tc, q,
                    )
                except ProviderUnavailableError:
                    continue
                best = max(candidates, key=lambda c: c.probability, default=None)
                if best is None or best.probability <= searched_best_prob:
                    continue  # only strictly better than the searched cell's best
                fare_delta = (
                    best.fare - searched_best_fare
                    if best.fare is not None and searched_best_fare is not None
                    else None
                )
                alternatives.append(
                    SwitchAlternative(
                        travel_class=tc,
                        quota=q,
                        availability=best.parsed,
                        probability=round(best.probability, 3),
                        fare=best.fare,
                        fare_delta=fare_delta,
                    )
                )
        alternatives.sort(key=lambda a: -a.probability)
        return alternatives[:MAX_ALTERNATIVES]

    async def _evaluate_pair(
        self,
        train_number: str,
        board: StationStop,
        alight: StationStop,
        km: dict[str, int],
        user_leg_km: int,
        user_leg_fare: int | None,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> _PairResult:
        raw = await self._provider.get_seat_status(
            train_number, board.code, alight.code, journey_date, travel_class, quota
        )
        parsed = parse_availability(raw)
        if parsed.status in (AvailabilityStatus.NOT_BOOKABLE, AvailabilityStatus.UNKNOWN):
            return _PairResult(board=board, alight=alight, parsed=parsed, candidate=None)

        booked_km = km[alight.code] - km[board.code]
        extra_km = booked_km - user_leg_km
        fare = await self._provider.get_fare(
            train_number, board.code, alight.code, journey_date, travel_class, quota
        )
        extra_fare = (
            fare - user_leg_fare
            if fare is not None and user_leg_fare is not None
            else None
        )
        probability = confirmation_probability(parsed)
        candidate = _Candidate(
            board=board,
            alight=alight,
            parsed=parsed,
            probability=probability,
            score=option_score(probability, extra_fare, user_leg_fare, extra_km, user_leg_km),
            booked_km=booked_km,
            extra_km=extra_km,
            fare=fare,
            extra_fare=extra_fare,
        )
        return _PairResult(board=board, alight=alight, parsed=parsed, candidate=candidate)

    def _build_recommendation(
        self, rank: int, cand: _Candidate, source: str, destination: str,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> Recommendation:
        requires_change = cand.board.code != source
        notes: list[str] = []
        quota_note = _QUOTA_NOTE.get(quota)
        if quota_note:
            notes.append(quota_note)
        if requires_change:
            notes.append(
                f"Change the boarding point to {source} on IRCTC immediately after booking — "
                "without it the TTE can mark you absent and release the berth."
            )
        if cand.extra_fare is not None and cand.extra_fare > 0:
            notes.append(
                f"Costs ₹{cand.extra_fare} more than the direct {source}→{destination} fare; "
                "the unused distance is not refundable."
            )
        if cand.alight.code != destination:
            notes.append(
                f"Get off at {destination}; the ticket runs on to {cand.alight.code} "
                "but the difference is not refunded."
            )

        action = f"Book {cand.board.code} to {cand.alight.code}, board at {source}"
        if cand.alight.code != destination:
            action += f", alight at {destination}"
        action += _QUOTA_ACTION_SUFFIX.get(quota, "")
        action += f". Status: {cand.parsed.label}"

        return Recommendation(
            rank=rank,
            book_from=cand.board.code,
            book_to=cand.alight.code,
            board_at=source,
            alight_at=destination,
            action=action,
            availability=cand.parsed,
            probability=round(cand.probability, 3),
            score=round(cand.score, 3),
            booked_distance_km=cand.booked_km,
            extra_km=cand.extra_km,
            fare=cand.fare,
            extra_fare=cand.extra_fare,
            requires_boarding_change=requires_change,
            notes=notes,
        )
