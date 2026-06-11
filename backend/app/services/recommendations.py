"""Orchestrates a search: enumerate covering pairs, fetch + parse each
status, rank, and build the top-3 response with human-readable actions."""
import datetime as dt
from dataclasses import dataclass

from app.core.pairs import enumerate_covering_pairs
from app.core.parser import parse_availability
from app.core.ranking import confirmation_probability, option_score
from app.exceptions import InvalidJourneyDateError, TrainNotFoundError
from app.providers.base import RailDataProvider
from app.schemas import (
    AvailabilityStatus,
    ParsedAvailability,
    Recommendation,
    RecommendationResponse,
    StationStop,
    UserLeg,
)

MAX_RECOMMENDATIONS = 3
ADVANCE_RESERVATION_DAYS = 60  # IRCTC ARP, 60 days excluding journey date (since Nov 2024)


@dataclass
class _Candidate:
    board: StationStop
    alight: StationStop
    parsed: ParsedAvailability
    probability: float
    score: float
    booked_km: int
    extra_km: int
    fare: int
    extra_fare: int


class RecommendationService:
    def __init__(self, provider: RailDataProvider) -> None:
        self._provider = provider

    def find_optimal_route(
        self,
        train_number: str,
        user_source: str,
        user_destination: str,
        journey_date: dt.date,
    ) -> RecommendationResponse:
        source = user_source.strip().upper()
        destination = user_destination.strip().upper()
        self._validate_date(journey_date)

        route = self._provider.get_route(train_number)
        if route is None:
            raise TrainNotFoundError(train_number)

        pairs = enumerate_covering_pairs(route, source, destination)
        km = {stop.code: stop.distance_km for stop in route.stations}
        user_leg_km = km[destination] - km[source]
        user_leg_fare = self._provider.get_fare(train_number, source, destination)

        candidates: list[_Candidate] = []
        user_leg_parsed: ParsedAvailability | None = None
        for board, alight in pairs:
            raw = self._provider.get_seat_status(train_number, board.code, alight.code, journey_date)
            parsed = parse_availability(raw)
            if board.code == source and alight.code == destination:
                user_leg_parsed = parsed
            if parsed.status in (AvailabilityStatus.NOT_BOOKABLE, AvailabilityStatus.UNKNOWN):
                continue
            booked_km = km[alight.code] - km[board.code]
            extra_km = booked_km - user_leg_km
            fare = self._provider.get_fare(train_number, board.code, alight.code)
            probability = confirmation_probability(parsed)
            candidates.append(
                _Candidate(
                    board=board,
                    alight=alight,
                    parsed=parsed,
                    probability=probability,
                    score=option_score(probability, extra_km, user_leg_km),
                    booked_km=booked_km,
                    extra_km=extra_km,
                    fare=fare,
                    extra_fare=fare - user_leg_fare,
                )
            )

        # Best score first; ties: higher raw probability, cheaper, shorter.
        candidates.sort(key=lambda c: (-c.score, -c.probability, c.extra_fare, c.extra_km))

        recommendations = [
            self._build_recommendation(rank, cand, source, destination)
            for rank, cand in enumerate(candidates[:MAX_RECOMMENDATIONS], start=1)
        ]
        return RecommendationResponse(
            train_number=route.train_number,
            train_name=route.train_name,
            journey_date=journey_date,
            user_leg=UserLeg(
                source=source,
                destination=destination,
                distance_km=user_leg_km,
                fare=user_leg_fare,
                availability=user_leg_parsed,
            ),
            pairs_evaluated=len(pairs),
            recommendations=recommendations,
        )

    def _validate_date(self, journey_date: dt.date) -> None:
        today = dt.date.today()
        if journey_date < today:
            raise InvalidJourneyDateError("Journey date is in the past")
        if journey_date > today + dt.timedelta(days=ADVANCE_RESERVATION_DAYS):
            raise InvalidJourneyDateError(
                f"Journey date is outside the {ADVANCE_RESERVATION_DAYS}-day advance reservation period"
            )

    def _build_recommendation(
        self, rank: int, cand: _Candidate, source: str, destination: str
    ) -> Recommendation:
        requires_change = cand.board.code != source
        notes: list[str] = []
        if requires_change:
            notes.append(
                f"Change the boarding point to {source} on IRCTC immediately after booking — "
                "without it the TTE can mark you absent and release the berth."
            )
        if cand.extra_fare > 0:
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
