"""Abstract provider protocol interface for railway data sources.

Defines the seam between recommendation algorithms and underlying data sources
(e.g., live IRCTC scrapers, prefetched browser caches, or test doubles).
"""

import datetime as dt
from typing import Protocol

from app.schemas import (
    BookingQuota,
    TrainRoute,
    TravelClass,
)


class RailDataProvider(Protocol):
    async def get_route(self, train_number: str) -> TrainRoute | None: ...

    async def get_seat_status(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> str: ...

    async def get_seat_prediction(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int: ...

    async def get_fare(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int: ...

    async def get_train_classes(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> list[str]: ...
