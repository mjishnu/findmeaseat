"""Cached confirmtkt segments: placeholders are refetched, never served as
"unavailable"; nothing is ever marked dead; failed or missing pairs are retried."""

import datetime as dt
import json

import pytest
from conftest import route_of, train_dict

from app.domain.dates import booking_day_today
from app.infrastructure.cache import RouteCache, SeatFinderSegmentCache, TrainSearchCache
from app.providers.prefetched.client import format_date, has_class_availability
from app.schemas import BookingQuota, FetchResult, ManifestResponse, TravelClass
from app.services import seat_finder

TRAIN = "16528"
ROUTE = route_of(
    TRAIN,
    [("CAN", 0, 0), ("TLY", 21, 0), ("BDJ", 43, 0), ("CLT", 90, 0), ("PGI", 115, 0),
     ("SRR", 176, 0), ("PGT", 220, 0), ("CBE", 274, 0), ("YPR", 662, 0)],
)
SRC, DST = "CLT", "PGT"

GOOD = {"availability": "AVAILABLE-0042", "availabilityDisplayName": "AVL 42", "fare": "400", "predictionPercentage": 100}
NULL = {"availability": None, "availabilityDisplayName": "", "fare": "400", "predictionPercentage": 0}


def segment(sl: dict, board: str = "", alight: str = "") -> dict:
    t = train_dict(TRAIN, board, alight, None)
    t["availabilityCache"]["SL"] = sl
    return t


@pytest.fixture
def day():
    return booking_day_today() + dt.timedelta(days=11)


async def manifest(day, travel_class=TravelClass.SL):
    await RouteCache.put(TRAIN, ROUTE)
    return await seat_finder.create_manifest(
        TRAIN, SRC, DST, day, travel_class, BookingQuota.GENERAL, False, 1.0, True
    )


def listed(fetch_id: str) -> str:
    board, alight, _ = fetch_id.split("|")
    return json.dumps({"data": {"trainList": [train_dict(TRAIN, board, alight, "AVAILABLE-0042")]}})


def test_class_availability_helper():
    assert has_class_availability(segment(GOOD), "SL")
    assert not has_class_availability(segment(NULL), "SL")
    assert has_class_availability(segment(NULL), "3A")  # other class still answered
    empty = {"availabilityCache": {}, "availabilityCacheTatkal": {}, "availabilityCacheForQuota": {}}
    assert not has_class_availability(empty, "SL")
    assert has_class_availability(segment(GOOD), "2A")  # not offered on a populated cache
    assert not has_class_availability(segment(GOOD), "SL", BookingQuota.TATKAL)


async def test_placeholders_are_refetched_and_search_cache_is_used(day):
    cold = await manifest(day)
    fids = [f.fetch_id for f in cold.fetches]
    assert len(fids) > 3

    # every pair cached as a placeholder; the user's direct pair has real data in search_seg
    for fid in fids:
        b, a, d = fid.split("|")
        await SeatFinderSegmentCache.put_field(b, a, d, None, TRAIN, segment(NULL, b, a))
    await TrainSearchCache.put_field(SRC, DST, format_date(day), None, TRAIN, segment(GOOD, SRC, DST))

    warm = await manifest(day)
    assert {f.fetch_id for f in warm.fetches} == set(fids) - {f"{SRC}|{DST}|{format_date(day)}"}

    # 3A is answered by the same cached segments: nothing to fetch but verification
    other = await manifest(day, TravelClass.AC3)
    assert not isinstance(other, ManifestResponse) or all(
        f.fetch_id.startswith("verify:") for f in other.fetches
    )


async def test_segment_for_another_station_is_not_a_cache_hit(day):
    cold = await manifest(day)
    b, a, d = cold.fetches[0].fetch_id.split("|")
    await SeatFinderSegmentCache.put_field(b, a, d, None, TRAIN, segment(GOOD, "SBC", a))
    warm = await manifest(day)
    assert cold.fetches[0].fetch_id in {f.fetch_id for f in warm.fetches}


async def test_no_response_shape_marks_anything_dead(day, redis):
    m = await manifest(day)
    ids = sorted(f.fetch_id for f in m.fetches)
    others_only = json.dumps({"data": {"trainList": [], "errorCode": 0, "totalTrains": 3}})
    errored = json.dumps({"data": {"trainList": [], "errorCode": 1}})
    odd = ids[1:6]
    results = [FetchResult(fetch_id=f, status=200, body=listed(f)) for f in ids if f not in odd]
    results += [
        FetchResult(fetch_id=odd[0], status=200, body=others_only),
        FetchResult(fetch_id=odd[1], status=200, body=errored),
        FetchResult(fetch_id=odd[2], status=429, body=""),
        FetchResult(fetch_id=odd[3], status=0, body=""),
        # odd[4] omitted entirely
    ]
    out = await seat_finder.process_manifest(m.manifest_id, results)
    assert out is not None
    assert [k async for k in redis.scan_iter("dead:*")] == []

    again = await manifest(day)
    assert set(odd) <= {f.fetch_id for f in again.fetches}


async def test_unknown_or_duplicate_fetch_ids_are_rejected(day):
    from app.exceptions import InvalidManifestError

    m = await manifest(day)
    fid = m.fetches[0].fetch_id
    with pytest.raises(InvalidManifestError):
        await seat_finder.process_manifest(
            m.manifest_id, [FetchResult(fetch_id="X|Y|01-01-2030", status=200, body="")]
        )
    m = await manifest(day)
    with pytest.raises(InvalidManifestError):
        await seat_finder.process_manifest(
            m.manifest_id,
            [FetchResult(fetch_id=fid, status=200, body=""), FetchResult(fetch_id=fid, status=200, body="")],
        )
