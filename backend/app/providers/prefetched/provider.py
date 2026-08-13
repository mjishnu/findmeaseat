from app.core.manifest_store import SeatFinderEntry
from app.providers.irctc.client import _to_int, cache_key, class_cache
from app.schemas import BookingQuota, TrainRoute


class PreFetchedProvider:
    """RailDataProvider that reads from pre-parsed confirmtkt trainList dicts.
    Data may come from browser fetches, segment cache, or both.

    The frontend pre-filters each trainList to only the target train, so
    _get_train just takes the first element from the list."""

    def __init__(
        self,
        entry: SeatFinderEntry,
        parsed_segments: dict[str, list[dict]],  # fetch_id -> trainList
    ) -> None:
        self._entry = entry
        self._parsed = parsed_segments

    def _get_train(self, source: str, destination: str) -> dict | None:
        """Return the (single) train dict for this segment, or None."""
        trains = self._parsed.get(f"{source}|{destination}", [])
        return trains[0] if trains else None

    async def get_route(self, train_number: str) -> TrainRoute | None:
        return self._entry.route

    async def get_seat_status(self, train_number, source, destination,
                               journey_date, travel_class,
                               quota=BookingQuota.GENERAL) -> str:
        train = self._get_train(source, destination)
        if train is None:
            return "NOT AVAILABLE"
        cache_entry = class_cache(train, travel_class.value, quota)
        display = cache_entry.get("availability") or cache_entry.get("availabilityDisplayName")
        return display or "NOT AVAILABLE"

    async def get_fare(self, train_number, source, destination,
                        journey_date, travel_class,
                        quota=BookingQuota.GENERAL) -> int:
        train = self._get_train(source, destination)
        if train is None:
            return -1
        return _to_int(class_cache(train, travel_class.value, quota).get("fare"))

    async def get_seat_prediction(self, train_number, source, destination,
                                    journey_date, travel_class,
                                    quota=BookingQuota.GENERAL) -> int:
        train = self._get_train(source, destination)
        if train is None:
            return -1
        return _to_int(class_cache(train, travel_class.value, quota).get("predictionPercentage"))

    async def get_train_classes(self, train_number, source, destination,
                                 journey_date,
                                 quota=BookingQuota.GENERAL) -> list[str]:
        train = self._get_train(source, destination)
        if train is None:
            return []
        cache = train.get(cache_key(quota)) or {}
        return [code for code, entry in cache.items()
                if isinstance(entry, dict) and (entry.get("availability") or entry.get("availabilityDisplayName"))]
