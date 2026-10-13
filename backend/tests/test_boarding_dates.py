"""Boarding dates are corrected from confirmtkt's timings when the route's (erail)
day offsets are stale, without ever using another day's train run."""

import datetime as dt

import pytest
from conftest import FakeConfirmtkt, picks, route_of, run_search

from app.domain.dates import booking_day_today
from app.infrastructure.cache import BoardDayCache
from app.providers.prefetched.parser import parse_availability

ONE = dt.timedelta(days=1)

# 22653-like: erail puts TVC/QLN a day before ERN; really TVC leaves 00:50, same date as ERN
STALE_ROUTE = route_of(
    "22653",
    [("TVC", 0, 0), ("QLN", 65, 0), ("ERN", 223, 1), ("TCR", 295, 1), ("NZM", 3159, 2)],
)
STALE_DEP = {"TVC": 50, "QLN": 110, "ERN": 310, "TCR": 380, "NZM": 2800}
STALE_ARR = {"QLN": 105, "ERN": 305, "TCR": 377, "NZM": 2800}


@pytest.fixture
def day():
    return booking_day_today() + dt.timedelta(days=12)


async def test_non_daily_train_with_stale_offsets_gets_every_board(day):
    fake = FakeConfirmtkt("22653", STALE_DEP, STALE_ARR, runs={day})
    resp, _ = await run_search(fake, STALE_ROUTE, "ERN", "NZM", day)

    assert day in {d for b, _, d in fake.calls if b == "TVC"}
    assert {("TVC", "NZM"), ("QLN", "NZM"), ("ERN", "NZM")} <= set(picks(resp))
    assert resp.pairs_skipped == 0
    assert await BoardDayCache.get("22653", "TVC", "ERN") == 0


async def test_daily_train_uses_the_users_run_not_another_days(day):
    fake = FakeConfirmtkt("22653", STALE_DEP, STALE_ARR, runs=None)
    resp, _ = await run_search(fake, STALE_ROUTE, "ERN", "NZM", day)

    want = parse_availability(fake.availability_for(day)).raw
    assert picks(resp)[("TVC", "NZM")].availability.raw == want


async def test_correct_offsets_cost_nothing_extra(day):
    route = route_of("16528", [("CAN", 0, 0), ("CLT", 90, 0), ("SA", 438, 1), ("YPR", 662, 1)])
    dep = {"CAN": 18 * 60 + 5, "CLT": 19 * 60 + 30, "SA": 1440 + 120, "YPR": 1440 + 360}
    arr = {"CLT": 19 * 60 + 25, "SA": 1440 + 115, "YPR": 1440 + 350}
    fake = FakeConfirmtkt("16528", dep, arr, runs=None)
    _, rounds = await run_search(fake, route, "SA", "YPR", day)

    assert len(fake.calls) == 3  # one per pair, no recheck round
    assert rounds == 2  # fetch + verify
    assert {d for b, _, d in fake.calls if b != "SA"} == {day - ONE}


async def test_unsold_station_substitution_and_failures(day, redis):
    route = route_of(
        "22691",
        [("SBC", 0, 0), ("YPR", 10, 0), ("MAD", 50, 0), ("TUM", 70, 0), ("NZM", 2000, 1)],
    )
    dep = {"SBC": 1200, "YPR": 1220, "MAD": 1260, "TUM": 1300, "NZM": 2640}
    arr = {"YPR": 1218, "MAD": 1258, "TUM": 1298, "NZM": 2640}
    fake = FakeConfirmtkt(
        "22691",
        dep,
        arr,
        runs={day},
        unsold={"MAD"},
        substitute={"YPR": "SBC"},
        fail={("SBC", "NZM")},
    )
    resp, _ = await run_search(fake, route, "TUM", "NZM", day)
    got = picks(resp)

    assert ("YPR", "NZM") not in got  # confirmtkt answered for SBC, not YPR
    assert ("MAD", "NZM") not in got
    assert ("TUM", "NZM") in got
    assert len([c for c in fake.calls if c[0] == "SBC"]) == 1  # a 429 isn't a date problem
    assert len([c for c in fake.calls if c[0] == "MAD"]) <= 3  # bounded recheck
    assert [k async for k in redis.scan_iter("sf_seg:YPR:*")] == []


async def test_repeat_search_is_served_from_cache(day):
    fake = FakeConfirmtkt("22653", STALE_DEP, STALE_ARR, runs={day})
    await run_search(fake, STALE_ROUTE, "ERN", "NZM", day)
    first = len(fake.calls)
    await run_search(fake, STALE_ROUTE, "ERN", "NZM", day)
    assert len(fake.calls) == first


async def test_stale_remembered_offset_is_corrected(day):
    await BoardDayCache.put("22653", "TVC", "ERN", 3)  # truth is 0
    fake = FakeConfirmtkt("22653", STALE_DEP, STALE_ARR, runs={day})
    resp, _ = await run_search(fake, STALE_ROUTE, "ERN", "NZM", day)

    assert await BoardDayCache.get("22653", "TVC", "ERN") == 0
    assert ("TVC", "NZM") in picks(resp)


async def test_never_adopts_another_days_run(day):
    # true boarding date not listed (e.g. departed); neighbouring days of a daily train are
    fake = FakeConfirmtkt(
        "22653", STALE_DEP, STALE_ARR, runs=None, blackout={("TVC", day - ONE), ("TVC", day)}
    )
    resp, _ = await run_search(fake, STALE_ROUTE, "ERN", "NZM", day)

    assert ("TVC", "NZM") not in picks(resp)
    assert await BoardDayCache.get("22653", "TVC", "ERN") in (None, 0)
