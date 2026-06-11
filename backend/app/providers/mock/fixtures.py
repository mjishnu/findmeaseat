"""Hard-coded demo data. This `mock` package is the ONLY place fake values
live; nothing outside providers/mock/ may import from it (tests excepted)."""
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

# Mock telescopic fare model: flat ₹/km discounted by total-distance slab,
# rounded to ₹5 with a class minimum — same shape as real IR fare tables.
_BASE_RATE_PER_KM = 1.30
_REBATE_SLABS: list[tuple[int, float]] = [(50, 0.0), (100, 0.05), (500, 0.15), (1000, 0.25), (1500, 0.30)]
_MAX_REBATE = 0.40
_MIN_FARE = 105


def calculate_fare(distance_km: int) -> int:
    rebate = _MAX_REBATE
    for limit, slab_rebate in _REBATE_SLABS:
        if distance_km <= limit:
            rebate = slab_rebate
            break
    fare = distance_km * _BASE_RATE_PER_KM * (1 - rebate)
    return max(_MIN_FARE, 5 * round(fare / 5))
