"""Train search between two stations.

Thin orchestration: validate the date, ask the provider for every train on the
leg (raw per-class offers for both quotas), then normalize each raw availability
string through the shared parser + ranking — so train-search availability reads
exactly like the seat-finder's.
"""

from app.core.parser import parse_availability
from app.core.ranking import confirmation_probability
from app.schemas import (
    ClassAvailability,
    RawClassOffer,
    RawTrainBetween,
    TrainBetween,
)


def to_train_between(raw: RawTrainBetween) -> TrainBetween:
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
        general=[to_class(o) for o in raw.general_offers],
        tatkal=[to_class(o) for o in raw.tatkal_offers],
        allowed_quotas=raw.allowed_quotas,
    )


def to_class(offer: RawClassOffer) -> ClassAvailability:
    parsed = parse_availability(offer.raw_availability)
    p = confirmation_probability(parsed, offer.prediction_pct)
    return ClassAvailability(
        travel_class=offer.travel_class,
        availability=parsed,
        probability=round(p, 3),
        fare=offer.fare or None,  # 0/None -> None: never render a misleading "₹0"
    )
