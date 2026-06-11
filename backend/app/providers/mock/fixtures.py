"""Hard-coded demo data. This `mock` package is the ONLY place fake values
live; nothing outside providers/mock/ may import from it (tests excepted)."""
import math

from app.schemas import StationStop, TrainRoute

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

# Stations owning a Remote Location quota on this route. Real trains define
# these per timetable; pairs touching one draw RLWL instead of PQWL.
REMOTE_LOCATIONS: frozenset[str] = frozenset({"D"})

# Mock telescopic fare model. Slabs apply MARGINALLY (each km billed at the
# rate of the slab it falls in) so fares stay monotone in distance — a
# whole-distance rebate would make a longer ticket cheaper at every slab
# boundary. Rounded UP to ₹5 with a class minimum, like real IR fare tables.
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
