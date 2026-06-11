"""Shared test doubles. StubProvider satisfies RailDataProvider structurally
and lets each test script exact availability strings per station pair."""
import datetime as dt

from app.providers.mock.fixtures import DEMO_TRAIN, calculate_fare
from app.schemas import TrainRoute


class StubProvider:
    def __init__(self, statuses: dict[tuple[str, str], str]):
        self._statuses = statuses

    def get_route(self, train_number: str) -> TrainRoute | None:
        return DEMO_TRAIN if train_number == DEMO_TRAIN.train_number else None

    def get_seat_status(
        self, train_number: str, source: str, destination: str, journey_date: dt.date
    ) -> str:
        return self._statuses.get((source, destination), "REGRET")

    def get_fare(self, train_number: str, source: str, destination: str) -> int:
        km = {s.code: s.distance_km for s in DEMO_TRAIN.stations}
        return calculate_fare(abs(km[destination] - km[source]))


def tomorrow() -> dt.date:
    return dt.date.today() + dt.timedelta(days=1)
