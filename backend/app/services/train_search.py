"""Train search between two stations.

Thin orchestration: validate the date, ask the provider for every train on the
leg (raw per-class offers for both quotas), then normalize each raw availability
string through the shared parser + ranking — so train-search availability reads
exactly like the seat-finder's.
"""
import datetime as dt

from app.core.dates import validate_journey_date
from app.core.parser import parse_availability
from app.core.ranking import confirmation_probability
from app.providers.base import RailDataProvider
from app.schemas import (
    BookingQuota,
    ClassAvailability,
    RawClassOffer,
    RawTrainBetween,
    TrainBetween,
    TrainQuotaClasses,
    TrainsBetweenResponse,
    TrainsQuotaAvailabilityResponse,
)


class TrainSearchService:
    def __init__(self, provider: RailDataProvider) -> None:
        self._provider = provider

    async def search(
        self, source: str, destination: str, journey_date: dt.date
    ) -> TrainsBetweenResponse:
        source = source.strip().upper()
        destination = destination.strip().upper()
        validate_journey_date(journey_date)
        raw_trains = await self._provider.search_trains_between(
            source, destination, journey_date
        )
        return TrainsBetweenResponse(
            source=source,
            destination=destination,
            journey_date=journey_date,
            trains=[self._to_train_between(t) for t in raw_trains],
        )

    async def search_quota(
        self, source: str, destination: str, journey_date: dt.date, quota: BookingQuota
    ) -> TrainsQuotaAvailabilityResponse:
        source = source.strip().upper()
        destination = destination.strip().upper()
        validate_journey_date(journey_date)
        rows = await self._provider.search_quota_availability(
            source, destination, journey_date, quota
        )
        return TrainsQuotaAvailabilityResponse(
            source=source,
            destination=destination,
            journey_date=journey_date,
            quota=quota,
            trains=[
                TrainQuotaClasses(
                    train_number=train_number,
                    from_code=from_code,
                    departure_time=departure_time,
                    classes=[self._to_class(o) for o in offers],
                )
                for train_number, from_code, departure_time, offers in rows
            ],
        )

    def _to_train_between(self, raw: RawTrainBetween) -> TrainBetween:
        return TrainBetween(
            train_number=raw.train_number,
            train_name=raw.train_name,
            from_code=raw.from_code,
            from_name=raw.from_name,
            to_code=raw.to_code,
            to_name=raw.to_name,
            departure_time=raw.departure_time,
            arrival_time=raw.arrival_time,
            duration_min=raw.duration_min,
            running_days=raw.running_days,
            has_pantry=raw.has_pantry,
            distance_km=raw.distance_km,
            general=[self._to_class(o) for o in raw.general_offers],
            tatkal=[self._to_class(o) for o in raw.tatkal_offers],
            allowed_quotas=raw.allowed_quotas,
        )

    @staticmethod
    def _to_class(offer: RawClassOffer) -> ClassAvailability:
        parsed = parse_availability(offer.raw_availability)
        p = confirmation_probability(parsed, offer.prediction_pct)
        return ClassAvailability(
            travel_class=offer.travel_class,
            availability=parsed,
            probability=round(p, 3) if p is not None else None,
            fare=offer.fare or None,  # 0/None -> None: never render a misleading "₹0"
        )
