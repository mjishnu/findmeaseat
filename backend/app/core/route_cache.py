import time
from app.schemas import TrainRoute

_cache: dict[str, tuple[float, TrainRoute]] = {}
_TTL = 60.0
_MAX_SIZE = 256

def get(train_number: str) -> TrainRoute | None:
    entry = _cache.get(train_number)
    if entry and time.monotonic() - entry[0] < _TTL:
        return entry[1]
    _cache.pop(train_number, None)
    return None

def put(train_number: str, route: TrainRoute) -> None:
    _cache[train_number] = (time.monotonic(), route)
    if len(_cache) > _MAX_SIZE:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        del _cache[oldest]
