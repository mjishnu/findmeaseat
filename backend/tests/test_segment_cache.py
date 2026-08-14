import datetime as dt
import pytest

from app.core.manifest_store import SeatFinderEntry
from app.core.redis import HashRedisCache
from app.providers.prefetched.provider import PreFetchedProvider
from app.schemas import BookingQuota, TravelClass


def test_prefetched_provider_train_matching():
    train_12424 = {"trainNumber": "12424", "trainName": "RAJDHANI"}
    train_12004 = {"trainNumber": "12004", "trainName": "SHATABDI"}

    entry = SeatFinderEntry(
        phase="fetch",
        route=None,
        pairs=[],
        fetch_id_to_pair={},
        cached_segments={},
        train_number="12424",
        user_source="DEL",
        user_destination="CNB",
        journey_date=dt.date(2026, 9, 1),
        travel_class=TravelClass.SL,
        quota=BookingQuota.GENERAL,
        partial=False,
        min_coverage_pct=100.0,
        require_connect=False,
    )

    # Segment has multiple trains cached (e.g. from General Search)
    parsed_segments = {
        "DEL|CNB": train_12424
    }

    provider = PreFetchedProvider(entry, parsed_segments)
    matched = provider._parsed.get("DEL|CNB")

    assert matched is not None
    assert matched["trainNumber"] == "12424"
    assert matched["trainName"] == "RAJDHANI"


def test_hash_redis_cache_key_generation():
    cache = HashRedisCache[dict](prefix="test_seg", ttl=3600)
    assert cache._key("DEL", "CNB", "01-09-2026", "GN") == "test_seg:DEL:CNB:01-09-2026:GN"
