from app.core.manifest_store import SeatFinderEntry
from app.providers.irctc.client import _to_int, cache_key, class_cache, find_train
from app.schemas import BookingQuota, TrainRoute


class PreFetchedProvider:
    """RailDataProvider that reads from pre-parsed confirmtkt trainList dicts.
    Data may come from browser fetches, segment cache, or both."""

    def __init__(
        self,
        entry: SeatFinderEntry,
        parsed_segments: dict[str, list[dict]],  # fetch_id -> trainList
    ) -> None:
        self._entry = entry
        self._parsed = parsed_segments

    async def get_route(self, train_number: str) -> TrainRoute | None:
        return self._entry.route

    async def get_seat_status(self, train_number, source, destination,
                               journey_date, travel_class,
                               quota=BookingQuota.GENERAL) -> str:
        fid = f"{source}|{destination}"
        train = find_train(self._parsed.get(fid, []), train_number)
        if train is None:
            return "NOT AVAILABLE"
        cache_entry = class_cache(train, travel_class.value, quota)
        display = cache_entry.get("availability") or cache_entry.get("availabilityDisplayName")
        return display or "NOT AVAILABLE"

    async def get_fare(self, train_number, source, destination,
                        journey_date, travel_class,
                        quota=BookingQuota.GENERAL) -> int | None:
        fid = f"{source}|{destination}"
        train = find_train(self._parsed.get(fid, []), train_number)
        if train is None:
            return None
        # Use .get() not [] to avoid KeyError; or None coerces 0 → None
        # matching the live provider (provider.py:178–183).
        return _to_int(class_cache(train, travel_class.value, quota).get("fare")) or None

    async def get_seat_prediction(self, train_number, source, destination,
                                    journey_date, travel_class,
                                    quota=BookingQuota.GENERAL) -> int | None:
        fid = f"{source}|{destination}"
        train = find_train(self._parsed.get(fid, []), train_number)
        if train is None:
            return None
        return _to_int(class_cache(train, travel_class.value, quota).get("predictionPercentage"))

    async def get_train_classes(self, train_number, source, destination,
                                 journey_date,
                                 quota=BookingQuota.GENERAL) -> list[str]:
        # The blob has ALL classes the train offers (not just the searched class).
        # Returning real codes lets RecommendationService._build_better_alternatives
        # work naturally — "switch to 3A" banners come for free.
        fid = f"{source}|{destination}"
        train = find_train(self._parsed.get(fid, []), train_number)
        if train is None:
            return []
        cache = train.get(cache_key(quota)) or {}
        return [code for code, entry in cache.items()
                if isinstance(entry, dict) and (entry.get("availability") or entry.get("availabilityDisplayName"))]
