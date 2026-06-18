"""In-memory station directory for autocomplete.

Static local data (NOT a RailDataProvider concern): the bundled
`app/data/stations.json` is loaded once and ranked per query. Ranking tiers,
best first: exact code, code prefix, name prefix, city prefix, name substring,
city substring. Keeping name ahead of city stops every station in a big city
(all sharing that city name) from crowding out the station actually named for it.
"""
import json
from pathlib import Path

from app.schemas import Station

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "stations.json"


class StationDirectory:
    def __init__(self, stations: list[Station]) -> None:
        self._stations = stations

    @classmethod
    def from_json(cls, path: Path = _DATA_PATH) -> "StationDirectory":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls([Station(**s) for s in raw])

    def search(self, query: str, limit: int = 8) -> list[Station]:
        q = query.strip()
        if not q:
            return []
        code_q = q.upper()
        text_q = q.lower()

        ranked: list[tuple[int, str, Station]] = []
        for s in self._stations:
            code = s.code.upper()
            name = s.name.lower()
            city = s.city.lower()
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
                continue
            ranked.append((tier, s.name, s))

        ranked.sort(key=lambda r: (r[0], r[1]))
        return [s for _tier, _name, s in ranked[:limit]]
