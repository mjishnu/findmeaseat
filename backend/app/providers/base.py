"""The seam between the app and its data source."""
import datetime as dt
from typing import Protocol

from app.schemas import TrainRoute


class RailDataProvider(Protocol):
    """Interface every data source must satisfy.

    providers/mock implements this today. To go live, implement these three
    methods against the real IRCTC API / a scraper / a DB in a sibling
    package (e.g. providers/irctc/) and change one line in app/dependencies.py.
    """

    def get_route(self, train_number: str) -> TrainRoute | None: ...

    def get_seat_status(
        self, train_number: str, source: str, destination: str, journey_date: dt.date
    ) -> str: ...

    def get_fare(self, train_number: str, source: str, destination: str) -> int: ...
