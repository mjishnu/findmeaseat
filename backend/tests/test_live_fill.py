"""confirmtkt's search API leaves availability null for many pairs until someone
checks them live; the seat finder live-checks those, caches the answer, and so a
repeat search needs no confirmtkt requests for them."""

import datetime as dt

import pytest
from conftest import FakeConfirmtkt, picks, route_of, run_search

from app.domain.dates import booking_day_today
from app.infrastructure.cache import TrainSearchCache
from app.providers.prefetched.client import format_date
from app.services import seat_finder

ROUTE = route_of("16528", [("CAN", 0, 0), ("CLT", 90, 0), ("PGT", 220, 0), ("YPR", 662, 0)])
DEP = {"CAN": 600, "CLT": 700, "PGT": 820, "YPR": 1300}
ARR = {"CLT": 695, "PGT": 815, "YPR": 1300}
NULLS = {("CAN", "YPR"), ("CLT", "YPR")}


@pytest.fixture
def day():
    return booking_day_today() + dt.timedelta(days=9)


async def test_null_pairs_are_checked_live_and_recommended(day):
    fake = FakeConfirmtkt("16528", DEP, ARR, placeholders=NULLS)
    resp, _ = await run_search(fake, ROUTE, "PGT", "YPR", day)

    assert {(b, a) for b, a, _ in fake.live_calls} == NULLS
    assert NULLS <= set(picks(resp))
    assert resp.pairs_no_data == 0


async def test_repeat_search_makes_no_confirmtkt_requests(day):
    fake = FakeConfirmtkt("16528", DEP, ARR, placeholders=NULLS)
    await run_search(fake, ROUTE, "PGT", "YPR", day)
    searches, lives = len(fake.calls), len(fake.live_calls)

    resp, _ = await run_search(fake, ROUTE, "PGT", "YPR", day)
    assert (len(fake.calls), len(fake.live_calls)) == (searches, lives)
    assert NULLS <= set(picks(resp))


async def test_live_checked_pairs_are_not_verified_twice(day):
    fake = FakeConfirmtkt("16528", DEP, ARR, placeholders=NULLS)
    await run_search(fake, ROUTE, "PGT", "YPR", day)
    assert fake.verify_calls == 1  # only PGT->YPR, which came from the search API


async def test_live_checks_are_capped_nearest_first(day, monkeypatch):
    monkeypatch.setattr(seat_finder, "MAX_LIVE_FILLS", 2)
    every = NULLS | {("PGT", "YPR")}
    fake = FakeConfirmtkt("16528", DEP, ARR, placeholders=every)
    resp, _ = await run_search(fake, ROUTE, "PGT", "YPR", day)

    assert {(b, a) for b, a, _ in fake.live_calls} == {("PGT", "YPR"), ("CLT", "YPR")}
    assert resp.pairs_no_data == 1  # CAN->YPR left unchecked this time


async def test_failed_live_check_is_no_data(day):
    fake = FakeConfirmtkt("16528", DEP, ARR, placeholders=NULLS, live_fail={("CAN", "YPR")})
    resp, _ = await run_search(fake, ROUTE, "PGT", "YPR", day)

    assert ("CAN", "YPR") not in picks(resp)
    assert ("CLT", "YPR") in picks(resp)
    assert resp.pairs_no_data == 1


async def test_verify_writes_live_answer_into_cache(day):
    # search API says AVAILABLE; the live check says otherwise
    fake = FakeConfirmtkt("16528", DEP, ARR, live_status="GNWL20/WL5")
    await run_search(fake, ROUTE, "PGT", "YPR", day, live_verify=True)
    searches = len(fake.calls)

    resp, _ = await run_search(fake, ROUTE, "PGT", "YPR", day)  # no live answers now
    assert len(fake.calls) == searches  # nothing deleted, so nothing refetched
    assert resp.user_leg.availability.raw == "WL 5"  # the cached live answer


async def test_trains_between_cache_is_updated_not_wiped(day, redis):
    key_parts = ("PGT", "YPR", format_date(day), None)
    full = {"trainNumber": "16528", "trainName": "KANNUR YPR EXP", "fromStnCode": "PGT", "toStnCode": "YPR",
            "departureTime": "13:40", "duration": 480,
            "availabilityCache": {"SL": {"availability": "AVAILABLE-0010", "fare": "300"}},
            "availabilityCacheTatkal": {}, "availabilityCacheForQuota": {}}
    other = dict(full, trainNumber="16562", trainName="OTHER EXP")
    await TrainSearchCache.put_many(*key_parts, {"16528": full, "16562": other})
    await redis.expire("search_seg:PGT:YPR:" + format_date(day), 600)

    fake = FakeConfirmtkt("16528", DEP, ARR, live_status="GNWL20/WL5")
    await run_search(fake, ROUTE, "PGT", "YPR", day, live_verify=True)

    cached = await TrainSearchCache.get_field(*key_parts, "16528")
    assert cached["trainName"] == "KANNUR YPR EXP"  # full trains-between entry kept
    assert cached["availabilityCache"]["SL"]["availability"] == "WL 5"
    assert await TrainSearchCache.get_field(*key_parts, "16562") == other  # other trains untouched
    assert 0 < await redis.ttl("search_seg:PGT:YPR:" + format_date(day)) <= 600  # expiry kept
