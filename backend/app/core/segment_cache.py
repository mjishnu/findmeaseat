import time

_cache: dict[tuple[str, str, str, str | None], tuple[float, list[dict]]] = {}
_TTL = 60.0
_MAX_SIZE = 512

def get(source: str, dest: str, date_str: str, fetch_group: str | None) -> list[dict] | None:
    key = (source, dest, date_str, fetch_group)
    entry = _cache.get(key)
    if entry and time.monotonic() - entry[0] < _TTL:
        return entry[1]
    _cache.pop(key, None)
    return None

def put(source: str, dest: str, date_str: str, fetch_group: str | None, train_list: list[dict]) -> None:
    key = (source, dest, date_str, fetch_group)
    _cache[key] = (time.monotonic(), train_list)
    if len(_cache) > _MAX_SIZE:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        del _cache[oldest]
