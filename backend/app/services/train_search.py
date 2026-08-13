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
    base = raw.model_dump(exclude={"general_offers", "tatkal_offers"})
    return TrainBetween(
        **base,
        general=[to_class(o) for o in raw.general_offers],
        tatkal=[to_class(o) for o in raw.tatkal_offers],
    )


def to_class(offer: RawClassOffer) -> ClassAvailability:
    parsed = parse_availability(offer.raw_availability)
    p = confirmation_probability(parsed, offer.prediction_pct)
    return ClassAvailability(
        travel_class=offer.travel_class,
        availability=parsed,
        probability=round(p, 3),
        fare=offer.fare,
    )
