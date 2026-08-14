"""Abstract provider protocol interface for railway data sources.

Defines the seam between recommendation algorithms and underlying data sources
(e.g., live IRCTC scrapers, prefetched browser caches, or test doubles).
"""

from typing import Protocol

from app.schemas import (
    BookingQuota,
    ParsedAvailability,
    TrainRoute,
    TravelClass,
)


class RailDataProvider(Protocol):
    async def get_route(self) -> TrainRoute | None: ...

    async def get_seat_status(
        self,
        source: str,
        destination: str,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> ParsedAvailability: ...

    async def get_seat_prediction(
        self,
        source: str,
        destination: str,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int: ...

    async def get_fare(
        self,
        source: str,
        destination: str,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int: ...

    async def get_train_classes(
        self,
        source: str,
        destination: str,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> list[TravelClass]: ...
