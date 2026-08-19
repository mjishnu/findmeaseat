"""In-memory station directory for autocomplete.

Static local data: `app/data/stations.json` is loaded once and cached with @lru_cache.
Ranking tiers, best first: exact code, code prefix, name prefix, city prefix,
name substring, city substring. Keeping name ahead of city stops every station in a big
city (all sharing that city name) from crowding out the station actually named for it.
"""

import json
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

from app.schemas import Station

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "stations.json"


@lru_cache(maxsize=1)
def load_stations(path: Path = _DATA_PATH) -> tuple[Station, ...]:
    """Load and parse the bundled station dataset into Station models once."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(Station(**s) for s in raw)


@lru_cache(maxsize=512)
def search_stations(query: str, limit: int = 8) -> tuple[Station, ...]:
    """Search stations by code, name, or city with fuzzy fallback ranking."""
    q = query.strip()
    if not q:
        return ()
    code_q = q.upper()
    text_q = q.lower()

    ranked: list[tuple[int, float, str, Station]] = []

    for s in load_stations():
        code = s.code.upper()
        name = s.name.lower()
        city = s.city.lower()
        score = 0.0
        if code == code_q:
            tier = 0
        elif code.startswith(code_q):
            tier = 1
        elif name.startswith(text_q):
            tier = 2
        elif city.startswith(text_q):
            tier = 3
        elif text_q in name:
            tier = 4
        elif text_q in city:
            tier = 5
        else:
            score = fuzz.WRatio(text_q, f"{name} {city}")
            if score < 65:
                continue
            tier = 6
        ranked.append((tier, -score, s.name, s))

    ranked.sort(key=lambda r: (r[0], r[1], r[2]))
    return tuple(s for *_, s in ranked[:limit])
