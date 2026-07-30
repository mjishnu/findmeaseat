"""Orchestrates a search: enumerate covering pairs, fetch + parse each
status concurrently, rank, and build the top-3 response with human-readable
actions."""

import asyncio
import datetime as dt
from dataclasses import dataclass

from app.core.dates import validate_journey_date
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
    RecommendationNoteCode,
    RecommendationResponse,
    StationStop,
    SwitchAlternative,
    TravelClass,
    UserLeg,
)

MAX_RECOMMENDATIONS = 3
MAX_ALTERNATIVES = 3


@dataclass
class _Candidate:
    board: StationStop
    alight: StationStop
    parsed: ParsedAvailability
    probability: float
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
        (
            candidates,
            user_leg_parsed,
            pairs_skipped,
            user_leg_fare,
        ) = await self._evaluate_class(
            train_number,
            pairs,
            source,
            destination,
            km,
            user_leg_km,
            journey_date,
            travel_class,
            quota,
        )

        candidates.sort(
            key=lambda c: (
                c.parsed.status,
                option_score(
                    c.probability, c.extra_fare, user_leg_fare, c.extra_km, user_leg_km
                ),
            ),
            reverse=True,
        )

        recommendations = [
            self._build_recommendation(rank, cand, source, destination, quota)
            for rank, cand in enumerate(candidates[:MAX_RECOMMENDATIONS], start=1)
        ]
        chosen_best = max(candidates, key=lambda c: c.probability, default=None)
        chosen_best_prob = chosen_best.probability if chosen_best else -1.0
        chosen_best_fare = chosen_best.fare if chosen_best else user_leg_fare
        alternatives = await self._build_better_alternatives(
            train_number,
            pairs,
            source,
            destination,
            km,
            user_leg_km,
            journey_date,
            travel_class,
            quota,
            chosen_best_prob,
            chosen_best_fare,
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
        (concurrently) and return (candidates, direct-leg status, skipped count, direct fare).
        """
        user_leg_fare = await self._provider.get_fare(
            train_number, source, destination, journey_date, travel_class, quota
        )
        raw_results = await asyncio.gather(
            *(
                self._evaluate_pair(
                    train_number,
                    board,
                    alight,
                    km,
                    user_leg_km,
                    user_leg_fare,
                    journey_date,
                    travel_class,
                    quota,
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
                raise r

        candidates = [r.candidate for r in results if r.candidate is not None]
        user_leg_parsed = next(
            (
                r.parsed
                for r in results
                if r.board.code == source and r.alight.code == destination
            ),
            None,
        )
        return candidates, user_leg_parsed, skipped, user_leg_fare

    async def _build_better_alternatives(
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
        """Build a list of better alternative classes than the current in the same quota(SL in WL10 vs 3A in AVL5)."""
        alternatives: list[SwitchAlternative] = []
        try:
            offered = await self._provider.get_train_classes(
                train_number, source, destination, journey_date, searched_quota
            )
        except ProviderUnavailableError:
            return alternatives
        for code in offered:
            try:
                tc = TravelClass(code)
            except ValueError:
                continue  # a class our enum doesn't model
            if tc == searched_class:
                continue  # skip the class the user already searched
            try:
                candidates, _parsed, _skipped, _cell_fare = await self._evaluate_class(
                    train_number,
                    pairs,
                    source,
                    destination,
                    km,
                    user_leg_km,
                    journey_date,
                    tc,
                    searched_quota,
                )
                candidates = [c for c in candidates if c.probability > 0]
            except ProviderUnavailableError:
                continue
            best = max(candidates, key=lambda c: c.probability, default=None)
            if best is None or best.probability <= searched_best_prob:
                continue  # only better than the searched class's best are kept others skipped
            fare_delta = (
                best.fare - searched_best_fare
                if best.fare is not None and searched_best_fare is not None
                else None
            )
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
        if parsed.status in (
            AvailabilityStatus.NOT_BOOKABLE,
            AvailabilityStatus.UNKNOWN,
        ):
            return _PairResult(
                board=board, alight=alight, parsed=parsed, candidate=None
            )

        extra_km = km[alight.code] - km[board.code] - user_leg_km
        fare = await self._provider.get_fare(
            train_number, board.code, alight.code, journey_date, travel_class, quota
        )
        prediction = await self._provider.get_seat_prediction(
            train_number, board.code, alight.code, journey_date, travel_class, quota
        )
        extra_fare = (
            fare - user_leg_fare
            if fare is not None and user_leg_fare is not None
            else None
        )
        probability = confirmation_probability(parsed, prediction)
        candidate = _Candidate(
            board=board,
            alight=alight,
            parsed=parsed,
            probability=probability,
            extra_km=extra_km,
            fare=fare,
            extra_fare=extra_fare,
        )
        return _PairResult(
            board=board, alight=alight, parsed=parsed, candidate=candidate
        )

    def _build_recommendation(
        self,
        rank: int,
        cand: _Candidate,
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

        if cand.extra_fare:
            notes.append(RecommendationNoteCode.EXTRA_FARE)
        if cand.probability < 0:
            notes.append(RecommendationNoteCode.MISSING_PREDICTION)
        if cand.board.code != source:
            notes.append(RecommendationNoteCode.BOARDING_CHANGE)
        if cand.alight.code != destination:
            notes.append(RecommendationNoteCode.ALIGHT_CHANGE)

        return Recommendation(
            rank=rank,
            book_from=cand.board.code,
            book_to=cand.alight.code,
            board_at=source,
            alight_at=destination,
            availability=cand.parsed,
            probability=round(cand.probability, 3),
            extra_km=cand.extra_km,
            fare=cand.fare,
            extra_fare=cand.extra_fare,
            notes=notes,
        )
