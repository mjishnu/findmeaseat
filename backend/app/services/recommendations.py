"""Orchestrates a search: enumerate covering pairs, fetch + parse each
status concurrently, rank, and build the top-3 response with human-readable
actions."""

import asyncio
import datetime as dt
import re
from dataclasses import dataclass

from app.core.dates import validate_journey_date
from app.core.pairs import enumerate_covering_pairs, enumerate_partial_pairs
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

MAX_VERIFY_CANDIDATES = 10
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
    coverage_pct: float = 1.0
    board_at: str = ""
    alight_at: str = ""


@dataclass
class _PairResult:
    board: StationStop
    alight: StationStop
    parsed: ParsedAvailability
    candidate: _Candidate | None


def _get_tiebreaker_score(cand: _Candidate) -> tuple[int, int]:
    m = re.search(r'\d+', cand.parsed.raw)
    num = int(m.group()) if m else 0
    if cand.parsed.status == AvailabilityStatus.WAITLIST:
        queue_score = -num
    else:
        queue_score = num
    return (queue_score, -cand.extra_km)


class RecommendationService:
    def __init__(self, provider: RailDataProvider) -> None:
        self._provider = provider

    async def rank_candidates(
        self,
        train_number: str,
        user_source: str,
        user_destination: str,
        journey_date: dt.date,
        travel_class: TravelClass = TravelClass.SL,
        quota: BookingQuota = BookingQuota.GENERAL,
        partial: bool = False,
        min_coverage_pct: float = 1.0,
        require_connect: bool = True,
    ) -> dict:
        source = user_source.strip().upper()
        destination = user_destination.strip().upper()
        validate_journey_date(journey_date)

        route = await self._provider.get_route(train_number)
        if route is None:
            raise TrainNotFoundError(train_number)

        pairs = enumerate_covering_pairs(route, source, destination)
        if partial:
            pairs = pairs + enumerate_partial_pairs(
                route, source, destination, min_coverage_pct, require_connect
            )
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

        # Compute coverage_pct for each candidate
        for c in candidates:
            start_code = c.board.code if km[c.board.code] > km[source] else source
            end_code = c.alight.code if km[c.alight.code] < km[destination] else destination
            c.board_at = start_code
            c.alight_at = end_code
            overlap_start_km = km[start_code]
            overlap_end_km = km[end_code]
            c.coverage_pct = (overlap_end_km - overlap_start_km) / user_leg_km if user_leg_km > 0 else 1.0

        def cand_sort_key(c: _Candidate, ul_fare: int | None) -> tuple:
            base_score = option_score(
                c.probability, c.extra_fare, ul_fare, c.extra_km, user_leg_km
            )
            return (
                round(base_score * c.coverage_pct, 4),
                c.parsed.status,
                c.coverage_pct,
                *_get_tiebreaker_score(c),
            )

        candidates.sort(
            key=lambda c: cand_sort_key(c, user_leg_fare),
            reverse=True,
        )

        chosen_best = candidates[0] if candidates else None
        chosen_best_key = cand_sort_key(chosen_best, user_leg_fare) if chosen_best else None
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
            chosen_best_key,
            chosen_best_fare,
        )
        
        # Serialize top 10 candidates
        serialized_candidates = [
            {
                "board": c.board.model_dump(),
                "alight": c.alight.model_dump(),
                "parsed": c.parsed.model_dump(),
                "probability": c.probability,
                "extra_km": c.extra_km,
                "fare": c.fare,
                "extra_fare": c.extra_fare,
                "coverage_pct": c.coverage_pct,
                "board_at": c.board_at,
                "alight_at": c.alight_at,
            }
            for c in candidates[:MAX_VERIFY_CANDIDATES]
        ]
        
        serialized_alternatives = [a.model_dump() for a in alternatives]
        
        user_leg_dict = {
            "source": source,
            "destination": destination,
            "distance_km": user_leg_km,
            "fare": user_leg_fare,
            "availability": user_leg_parsed.model_dump() if user_leg_parsed else None,
        }
        
        context = {
            "train_number": route.train_number,
            "train_name": route.train_name,
            "journey_date": journey_date.isoformat(),
            "travel_class": travel_class.value,
            "quota": quota.value,
            "user_leg": user_leg_dict,
            "pairs_evaluated": len(pairs),
            "pairs_skipped": pairs_skipped,
            "partial": partial,
            "min_coverage_pct": min_coverage_pct,
        }
        
        return {
            "candidates": serialized_candidates,
            "alternatives": serialized_alternatives,
            "context": context
        }

    def build_verified_response(
        self,
        ranked_data: dict,
        live_overrides: dict[str, dict] | None = None
    ) -> RecommendationResponse:
        """Re-rank top-10 candidates with live data, returning the final top-3."""
        live_overrides = live_overrides or {}
        context = ranked_data["context"]
        source = context["user_leg"]["source"]
        destination = context["user_leg"]["destination"]
        user_leg_km = context["user_leg"]["distance_km"]
        user_leg_fare = context["user_leg"]["fare"]
        quota = BookingQuota(context["quota"])
        
        updated_candidates: list[_Candidate] = []
        
        for cand_dict in ranked_data["candidates"]:
            board = StationStop(**cand_dict["board"])
            alight = StationStop(**cand_dict["alight"])
            parsed = ParsedAvailability(**cand_dict["parsed"])
            probability = cand_dict["probability"]
            fare = cand_dict["fare"]
            
            fetch_id = f"{board.code}|{alight.code}"
            
            if fetch_id in live_overrides:
                override = live_overrides[fetch_id]
                if "availability" in override:
                    parsed = override["availability"]
                if "prediction_pct" in override:
                    probability = confirmation_probability(parsed, override["prediction_pct"])
                else:
                    probability = confirmation_probability(parsed, None)
                if "fare" in override:
                    fare = override["fare"]

            extra_fare = (
                fare - user_leg_fare
                if fare is not None and user_leg_fare is not None
                else None
            )
            # Clamp negative extra_fare to None for partial pairs (shorter booking)
            if extra_fare is not None and extra_fare < 0:
                extra_fare = None

            updated_candidates.append(_Candidate(
                board=board,
                alight=alight,
                parsed=parsed,
                probability=probability,
                extra_km=cand_dict["extra_km"],
                fare=fare,
                extra_fare=extra_fare,
                coverage_pct=cand_dict.get("coverage_pct", 1.0),
                board_at=cand_dict.get("board_at", ""),
                alight_at=cand_dict.get("alight_at", ""),
            ))
            
        def verified_sort_key(c: _Candidate) -> tuple:
            base_score = option_score(
                c.probability, c.extra_fare, user_leg_fare, c.extra_km, user_leg_km
            )
            return (
                round(base_score * c.coverage_pct, 4),
                c.parsed.status,
                c.coverage_pct,
                *_get_tiebreaker_score(c),
            )

        updated_candidates.sort(
            key=verified_sort_key,
            reverse=True,
        )

        recommendations = [
            self._build_recommendation(rank, cand, source, destination, quota)
            for rank, cand in enumerate(updated_candidates[:MAX_RECOMMENDATIONS], start=1)
        ]

        alternatives = [SwitchAlternative(**a) for a in ranked_data["alternatives"]]
        user_leg = UserLeg(**context["user_leg"])

        return RecommendationResponse(
            train_number=context["train_number"],
            train_name=context["train_name"],
            journey_date=dt.date.fromisoformat(context["journey_date"]),
            travel_class=TravelClass(context["travel_class"]),
            quota=quota,
            user_leg=user_leg,
            pairs_evaluated=context["pairs_evaluated"],
            pairs_skipped=context["pairs_skipped"],
            recommendations=recommendations,
            alternatives=alternatives,
            partial=context.get("partial", False),
            min_coverage_pct=context.get("min_coverage_pct", 1.0),
        )

    async def find_optimal_route(
        self,
        train_number: str,
        user_source: str,
        user_destination: str,
        journey_date: dt.date,
        travel_class: TravelClass = TravelClass.SL,
        quota: BookingQuota = BookingQuota.GENERAL,
        partial: bool = False,
        min_coverage_pct: float = 1.0,
        require_connect: bool = True,
    ) -> RecommendationResponse:
        ranked_data = await self.rank_candidates(
            train_number, user_source, user_destination, journey_date,
            travel_class, quota, partial, min_coverage_pct, require_connect,
        )
        return self.build_verified_response(ranked_data)

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
        searched_best_key: tuple | None,
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
                for c in candidates:
                    start_code = c.board.code if km[c.board.code] > km[source] else source
                    end_code = c.alight.code if km[c.alight.code] < km[destination] else destination
                    c.board_at = start_code
                    c.alight_at = end_code
                    overlap_start_km = km[start_code]
                    overlap_end_km = km[end_code]
                    c.coverage_pct = (overlap_end_km - overlap_start_km) / user_leg_km if user_leg_km > 0 else 1.0

                candidates = [c for c in candidates if c.probability > 0]
            except ProviderUnavailableError:
                continue

            if not candidates:
                continue

            def alt_sort_key(c: _Candidate) -> tuple:
                base_score = option_score(
                    c.probability, c.extra_fare, _cell_fare, c.extra_km, user_leg_km
                )
                return (
                    round(base_score * c.coverage_pct, 4),
                    c.parsed.status,
                    c.coverage_pct,
                    *_get_tiebreaker_score(c),
                )

            best = max(candidates, key=alt_sort_key)
            if searched_best_key is not None and alt_sort_key(best) <= searched_best_key:
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

        extra_km = max(0, km[alight.code] - km[board.code] - user_leg_km)
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
        # Clamp negative extra_fare to None for partial pairs (shorter booking)
        if extra_fare is not None and extra_fare < 0:
            extra_fare = None
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
