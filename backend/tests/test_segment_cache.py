import datetime as dt
import pytest

from app.core.manifest_store import SeatFinderEntry
from app.core.redis import FlagCache, HashRedisCache
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


def test_full_search_flag_cache_key_generation():
    cache = FlagCache(prefix="full_search", ttl=3600)
    assert cache._key("DEL", "CNB", "01-09-2026", "GN") == "full_search:DEL:CNB:01-09-2026:GN"


def test_dead_pair_flag_cache_key_generation():
    cache = FlagCache(prefix="dead", ttl=3600)
    assert cache._key("12424", "DEL", "CNB", "01-09-2026") == "dead:12424:DEL:CNB:01-09-2026"



@pytest.mark.asyncio
async def test_train_search_manifest_cache_behavior(monkeypatch):
    from app.routers.train_search import trains_between_manifest
    from app.schemas import BookingQuota, ManifestResponse, TrainsBetweenResponse, TrainSearchManifestRequest

    req = TrainSearchManifestRequest(
        source="NDLS",
        destination="CNB",
        date=dt.date(2026, 9, 1),
        quota=BookingQuota.GENERAL,
    )

    # Case 1: FullSearchCache is False, but SegmentCache has 1 partial train
    async def mock_full_search_get_false(*args):
        return False

    async def mock_segment_cache_get_all(*args):
        return [{"trainNumber": "12345", "trainName": "TEST EXP", "departureTime": "10:00", "duration": 120, "fromStnCode": "NDLS", "toStnCode": "CNB"}]

    monkeypatch.setattr("app.routers.train_search.FullSearchCache.get", mock_full_search_get_false)
    monkeypatch.setattr("app.routers.train_search.SegmentCache.get_all", mock_segment_cache_get_all)

    resp = await trains_between_manifest(req)
    # Must return ManifestResponse (cache miss), not partial TrainsBetweenResponse
    assert isinstance(resp, ManifestResponse)

    # Case 2: FullSearchCache is True and SegmentCache has trains
    async def mock_full_search_get_true(*args):
        return True

    monkeypatch.setattr("app.routers.train_search.FullSearchCache.get", mock_full_search_get_true)

    resp2 = await trains_between_manifest(req)
    # Must return TrainsBetweenResponse directly from cache
    assert isinstance(resp2, TrainsBetweenResponse)
    assert len(resp2.trains) == 1


