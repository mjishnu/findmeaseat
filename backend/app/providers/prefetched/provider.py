"""RailDataProvider that reads from pre-parsed confirmtkt train dicts."""

from app.infrastructure.manifest_store import SeatFinderEntry
from app.providers.base import RailDataProvider
from app.providers.prefetched.client import _to_int, quota_cache_key, quota_class_cache
from app.providers.prefetched.parser import parse_availability
from app.schemas import BookingQuota, ParsedAvailability, TrainRoute, TravelClass


class PreFetchedProvider(RailDataProvider):
    """RailDataProvider that reads from pre-parsed confirmtkt train dicts."""

    def __init__(
        self,
        entry: SeatFinderEntry,
        parsed_segments: dict[str, dict],  # fetch_id -> train dict
    ) -> None:
        self._entry = entry
        self._parsed = parsed_segments

    async def get_route(self) -> TrainRoute | None:
        return self._entry.route

    async def get_seat_status(
        self,
        source: str,
        destination: str,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> ParsedAvailability:
        train = self._parsed.get(f"{source}|{destination}")
        if train is None:
            return parse_availability("NOT AVAILABLE")
        cache_entry = quota_class_cache(train, travel_class.value, quota)
        display = cache_entry.get("availability") or cache_entry.get(
            "availabilityDisplayName"
        )
        return parse_availability(display or "NOT AVAILABLE")

    async def get_fare(
        self,
        source: str,
        destination: str,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int:
        train = self._parsed.get(f"{source}|{destination}")
        if train is None:
            return -1
        return _to_int(quota_class_cache(train, travel_class.value, quota).get("fare"))

    async def get_seat_prediction(
        self,
        source: str,
        destination: str,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int:
        train = self._parsed.get(f"{source}|{destination}")
        if train is None:
            return -1
        return _to_int(
            quota_class_cache(train, travel_class.value, quota).get(
                "predictionPercentage"
            )
        )

    async def get_train_classes(
        self,
        source: str,
        destination: str,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> list[TravelClass]:
        train = self._parsed.get(f"{source}|{destination}")
        if train is None:
            return []
        cache = train.get(quota_cache_key(quota)) or {}
        classes: list[TravelClass] = []
        for code, entry in cache.items():
            if isinstance(entry, dict) and (
                entry.get("availability") or entry.get("availabilityDisplayName")
            ):
                try:
                    classes.append(TravelClass(code))
                except ValueError:
                    continue
        return classes
