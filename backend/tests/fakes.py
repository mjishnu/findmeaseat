"""Offline test doubles. These live under tests/ (never imported by app code)
so the application itself has no fake/demo data path — the only runtime data
source is the live IRCTC provider. A deterministic fake keeps tests fast and
network-free.
"""
import datetime as dt
import math
import random

from app.core.dates import booking_day_today
from app.schemas import (
    BookingQuota,
    RawClassOffer,
    RawTrainBetween,
    StationStop,
    TrainRoute,
    TravelClass,
)

# Tatkal opens ~1 day before travel, so distant-date Tatkal cells are empty.
TATKAL_WINDOW_DAYS = 1


def tatkal_open(journey_date: dt.date) -> bool:
    return (journey_date - booking_day_today()).days <= TATKAL_WINDOW_DAYS

DEMO_TRAIN = TrainRoute(
    train_number="12345",
    train_name="Demo Express",
    stations=[
        StationStop(code="A", name="Alipore Junction", distance_km=0),
        StationStop(code="B", name="Barwadih", distance_km=120),
        StationStop(code="C", name="Chandrapur", distance_km=310),
        StationStop(code="D", name="Daund Junction", distance_km=480),
        StationStop(code="E", name="Erode Junction", distance_km=750),
        StationStop(code="F", name="Firozpur City", distance_km=1020),
    ],
)

TRAINS: dict[str, TrainRoute] = {DEMO_TRAIN.train_number: DEMO_TRAIN}

# Stations owning a Remote Location quota on this route; pairs touching one draw
# RLWL instead of PQWL.
REMOTE_LOCATIONS: frozenset[str] = frozenset({"D"})

# Telescopic fare model. Slabs apply MARGINALLY (each km billed at the rate of
# the slab it falls in) so fares stay monotone in distance. Rounded UP to ₹5
# with a class minimum, like real IR fare tables.
_BASE_RATE_PER_KM = 1.30
_SLAB_RATES: list[tuple[int, float]] = [  # (slab upper bound km, rate multiplier)
    (50, 1.00),
    (100, 0.95),
    (500, 0.85),
    (1000, 0.75),
    (1500, 0.70),
]
_TAIL_RATE = 0.60  # beyond the last slab bound
_MIN_FARE = 105


def calculate_fare(distance_km: int) -> int:
    units = 0.0
    prev_bound = 0
    for bound, rate in _SLAB_RATES:
        span = min(distance_km, bound) - prev_bound
        if span <= 0:
            break
        units += span * rate
        prev_bound = bound
    if distance_km > _SLAB_RATES[-1][0]:
        units += (distance_km - _SLAB_RATES[-1][0]) * _TAIL_RATE
    fare = units * _BASE_RATE_PER_KM
    return max(_MIN_FARE, 5 * math.ceil(fare / 5))


class FakeRailDataProvider:
    """Deterministic RailDataProvider used only in tests. Seeding random.Random
    with the full query string makes results look random but stay identical for
    repeated calls, so tests are stable."""

    async def get_route(self, train_number: str) -> TrainRoute | None:
        return TRAINS.get(train_number)

    async def get_fare(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int | None:
        km = {s.code: s.distance_km for s in TRAINS[train_number].stations}
        base = calculate_fare(abs(km[destination] - km[source]))
        # Tatkal carries a premium; closed (distant-date) cells aren't priced.
        if quota is BookingQuota.TATKAL:
            return None if not tatkal_open(journey_date) else 5 * math.ceil(base * 1.3 / 5)
        return base

    async def get_seat_status(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> str:
        # Tatkal isn't populated until ~1 day before travel — distant dates show
        # nothing, exactly like the live source.
        if quota is BookingQuota.TATKAL and not tatkal_open(journey_date):
            return "NOT AVAILABLE"
        codes = [s.code for s in TRAINS[train_number].stations]
        i, j = codes.index(source), codes.index(destination)
        rng = random.Random(
            f"{train_number}|{source}|{destination}|{journey_date.isoformat()}"
            f"|{travel_class.value}|{quota.value}"
        )
        if i == 0:
            quota, p_available = "GNWL", 0.40
        elif j == len(codes) - 1 or source in REMOTE_LOCATIONS or destination in REMOTE_LOCATIONS:
            quota, p_available = "RLWL", 0.15
        else:
            quota, p_available = "PQWL", 0.10

        roll = rng.random()
        if roll < 0.08:
            return "REGRET"
        if roll < 0.08 + p_available:
            seats = rng.randint(1, 60)
            return rng.choice([f"AVAILABLE-{seats:04d}", f"AVAILABLE {seats}"])
        series = rng.randint(2, 40)
        current = rng.randint(1, series)
        return rng.choice([f"{quota}{series}/WL{current}", f"{quota} {series}/WL {current}"])

    # Fare multipliers per class for the synthetic options.
    _CLASS_FARE_MULT = {"SL": 1.0, "3A": 2.6, "2A": 3.8}

    async def get_class_options(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> list[tuple[str, str, int | None]]:
        # A distant-date Tatkal window offers no classes at all.
        if quota is BookingQuota.TATKAL and not tatkal_open(journey_date):
            return []
        km = {s.code: s.distance_km for s in TRAINS[train_number].stations}
        base = calculate_fare(abs(km[destination] - km[source]))
        out: list[tuple[str, str, int | None]] = []
        for code, mult in self._CLASS_FARE_MULT.items():
            status = await self.get_seat_status(
                train_number, source, destination, journey_date, TravelClass(code), quota
            )
            out.append((code, status, int(base * mult)))
        return out

    async def search_quota_availability(
        self,
        source: str,
        destination: str,
        journey_date: dt.date,
        quota: BookingQuota = BookingQuota.LADIES,
    ) -> list[tuple[str, str, str, list[RawClassOffer]]]:
        route = DEMO_TRAIN
        by_code = {s.code: s for s in route.stations}
        if source not in by_code or destination not in by_code:
            return []
        base = await self.get_fare(
            route.train_number, source, destination, journey_date, TravelClass.SL, quota
        )
        offers = [
            RawClassOffer(
                travel_class=TravelClass(code),
                raw_availability=await self.get_seat_status(
                    route.train_number, source, destination, journey_date, TravelClass(code), quota
                ),
                fare=int((base or 0) * mult),
            )
            for code, mult in self._CLASS_FARE_MULT.items()
        ]
        return [(route.train_number, source, "06:00", offers)]

    async def search_trains_between(
        self,
        source: str,
        destination: str,
        journey_date: dt.date,
    ) -> list[RawTrainBetween]:
        route = DEMO_TRAIN
        by_code = {s.code: s for s in route.stations}
        if source not in by_code or destination not in by_code:
            return []
        base = await self.get_fare(route.train_number, source, destination, journey_date, TravelClass.SL)
        offers = [
            RawClassOffer(
                travel_class=TravelClass(code),
                raw_availability=await self.get_seat_status(
                    route.train_number, source, destination, journey_date, TravelClass(code)
                ),
                fare=int(base * mult),
            )
            for code, mult in self._CLASS_FARE_MULT.items()
        ]
        return [
            RawTrainBetween(
                train_number=route.train_number,
                train_name=route.train_name,
                from_code=source,
                from_name=by_code[source].name,
                to_code=destination,
                to_name=by_code[destination].name,
                departure_time="06:00",
                arrival_time="20:00",
                duration_min=None,
                running_days="1111111",
                has_pantry=False,
                distance_km=abs(by_code[destination].distance_km - by_code[source].distance_km),
                general_offers=offers,
                tatkal_offers=[],
            )
        ]
