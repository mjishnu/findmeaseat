"""Shared test doubles. StubProvider satisfies RailDataProvider structurally
and lets each test script exact availability strings per station pair."""
import datetime as dt

from app.schemas import BookingQuota, TrainRoute, TravelClass
from tests.fakes import DEMO_TRAIN, calculate_fare
from app.services.recommendations import booking_day_today


class StubProvider:
    def __init__(
        self,
        statuses: dict[tuple, str],
        class_options: dict[str, int | None] | None = None,
        tatkal_class_options: dict[str, int | None] | None = None,
        predictions: dict[tuple, int] | None = None,
    ):
        # statuses keyed by (source, destination), (source, destination, class_code),
        # or (source, destination, class_code, quota_code) — most specific wins.
        self._statuses = statuses
        # Classes offered per quota: {class_code: direct_fare}. Default none, so
        # existing tests get no alternatives; tatkal defaults empty, modelling a
        # distant date where Tatkal isn't populated yet.
        self._class_options = class_options or {}
        self._tatkal_class_options = tatkal_class_options or {}
        # Keyed like statuses: (src,dst), (src,dst,class), or (src,dst,class,quota).
        self._predictions = predictions or {}

    async def get_route(self, train_number: str) -> TrainRoute | None:
        return DEMO_TRAIN if train_number == DEMO_TRAIN.train_number else None

    async def get_class_options(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> list[tuple[str, str, int | None]]:
        options = (
            self._tatkal_class_options
            if quota is BookingQuota.TATKAL
            else self._class_options
        )
        out: list[tuple[str, str, int | None]] = []
        for code, fare in options.items():
            status = await self.get_seat_status(
                train_number, source, destination, journey_date, TravelClass(code), quota
            )
            out.append((code, status, fare))
        return out

    async def get_seat_status(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> str:
        return (
            self._statuses.get((source, destination, travel_class.value, quota.value))
            or self._statuses.get((source, destination, travel_class.value))
            or self._statuses.get((source, destination))
            or "REGRET"
        )

    async def get_seat_prediction(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int | None:
        for key in (
            (source, destination, travel_class.value, quota.value),
            (source, destination, travel_class.value),
            (source, destination),
        ):
            if key in self._predictions:
                return self._predictions[key]  # explicit: a real 0 is preserved
        return None

    async def get_fare(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int:
        km = {s.code: s.distance_km for s in DEMO_TRAIN.stations}
        return calculate_fare(abs(km[destination] - km[source]))

    async def search_trains_between(self, source, destination, journey_date):
        # StubProvider drives the seat-finder tests; train search has its own
        # dedicated fakes, so this stays an empty (but structurally complete) stub.
        return []

    async def search_quota_availability(self, source, destination, journey_date, quota):
        # Train search has dedicated fakes; the seat-finder tests don't use this.
        return []


def tomorrow() -> dt.date:
    # Anchored to the same IST clock the service validates against.
    return booking_day_today() + dt.timedelta(days=1)
