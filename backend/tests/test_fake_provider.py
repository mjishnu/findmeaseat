"""Tests for the offline test double (tests/fakes.py) the suite relies on."""
import datetime as dt

import pytest

from app.core.parser import parse_availability
from app.schemas import AvailabilityStatus, BookingQuota, Quota, TravelClass
from app.services.recommendations import booking_day_today
from tests.fakes import FakeRailDataProvider, calculate_fare

DATE = dt.date(2026, 7, 1)
SL = TravelClass.SL
GN, TQ = BookingQuota.GENERAL, BookingQuota.TATKAL


@pytest.fixture()
def provider() -> FakeRailDataProvider:
    return FakeRailDataProvider()


async def test_route_lookup(provider):
    route = await provider.get_route("12345")
    assert route is not None
    assert [s.code for s in route.stations] == ["A", "B", "C", "D", "E", "F"]
    assert await provider.get_route("99999") is None


async def test_seat_status_is_deterministic(provider):
    first = await provider.get_seat_status("12345", "C", "D", DATE, SL)
    second = await provider.get_seat_status("12345", "C", "D", DATE, SL)
    assert first == second


async def test_seat_status_varies_by_class(provider):
    diverged = False
    for day in range(1, 20):
        date = dt.date(2026, 7, day)
        sl = await provider.get_seat_status("12345", "C", "D", date, TravelClass.SL)
        ac = await provider.get_seat_status("12345", "C", "D", date, TravelClass.AC2)
        if sl != ac:
            diverged = True
            break
    assert diverged


async def test_seat_status_is_always_parseable(provider):
    codes = ["A", "B", "C", "D", "E", "F"]
    for i, src in enumerate(codes):
        for dst in codes[i + 1 :]:
            parsed = parse_availability(await provider.get_seat_status("12345", src, dst, DATE, SL))
            assert parsed.status is not AvailabilityStatus.UNKNOWN


async def test_quota_mirrors_real_mechanics(provider):
    """Origin pairs draw GNWL; remote-location/terminus pairs RLWL; the rest PQWL."""
    for day in range(1, 15):
        date = dt.date(2026, 7, day)
        for src, dst, expected in [
            ("A", "D", Quota.GNWL),   # from origin
            ("B", "F", Quota.RLWL),   # to terminus
            ("C", "D", Quota.RLWL),   # D is a remote-location station
            ("B", "C", Quota.PQWL),   # intermediate → intermediate
        ]:
            parsed = parse_availability(await provider.get_seat_status("12345", src, dst, date, SL))
            if parsed.status is AvailabilityStatus.WAITLIST:
                assert parsed.quota == expected, f"{src}->{dst} on {date}"


def test_fare_is_telescopic_rounded_and_floored():
    assert calculate_fare(10) == 105                       # class minimum
    assert calculate_fare(170) == 205                      # (50·1.0 + 50·0.95 + 70·0.85)·1.30 → next ₹5
    assert calculate_fare(1020) < calculate_fare(510) * 2  # concave: long legs cheaper per km
    fares = [calculate_fare(km) for km in (50, 120, 310, 480, 750, 1020)]
    assert fares == sorted(fares)                          # monotonic
    assert all(f % 5 == 0 for f in fares)                  # rounded to ₹5


def test_fare_is_monotonic_across_slab_boundaries():
    for boundary in (50, 100, 500, 1000, 1500):
        window = [calculate_fare(km) for km in range(boundary - 2, boundary + 3)]
        assert window == sorted(window), f"fare inversion around {boundary} km"


async def test_fare_provider_uses_route_distance(provider):
    fare = await provider.get_fare("12345", "C", "D", DATE, SL)
    assert fare == calculate_fare(170)  # 480 − 310


async def test_search_trains_between_offers_are_parseable(provider):
    raws = await provider.search_trains_between("A", "D", DATE)
    assert len(raws) == 1
    raw = raws[0]
    assert raw.train_number == "12345"
    assert (raw.from_code, raw.to_code) == ("A", "D")
    assert raw.general_offers
    for offer in raw.general_offers:
        parsed = parse_availability(offer.raw_availability)
        assert parsed.status is not AvailabilityStatus.UNKNOWN


async def test_search_trains_between_unknown_station_is_empty(provider):
    assert await provider.search_trains_between("A", "Z", DATE) == []


async def test_tatkal_is_empty_for_a_distant_date(provider):
    # Tatkal opens ~1 day before travel; a distant date offers nothing.
    distant = booking_day_today() + dt.timedelta(days=30)
    assert await provider.get_class_options("12345", "A", "D", distant, TQ) == []
    status = await provider.get_seat_status("12345", "A", "D", distant, SL, TQ)
    assert parse_availability(status).status is AvailabilityStatus.NOT_BOOKABLE
    assert await provider.get_fare("12345", "A", "D", distant, SL, TQ) is None


async def test_tatkal_is_populated_within_the_window(provider):
    near = booking_day_today() + dt.timedelta(days=1)
    opts = await provider.get_class_options("12345", "A", "D", near, TQ)
    assert opts  # non-empty within the Tatkal window
    fare = await provider.get_fare("12345", "A", "D", near, SL, TQ)
    gn_fare = await provider.get_fare("12345", "A", "D", near, SL, GN)
    assert fare is not None and fare > gn_fare  # Tatkal carries a premium


async def test_tatkal_status_can_differ_from_general(provider):
    near = booking_day_today() + dt.timedelta(days=1)
    diverged = False
    codes = ["A", "B", "C", "D", "E", "F"]
    for i, src in enumerate(codes):
        for dst in codes[i + 1 :]:
            gn = await provider.get_seat_status("12345", src, dst, near, SL, GN)
            tq = await provider.get_seat_status("12345", src, dst, near, SL, TQ)
            if gn != tq:
                diverged = True
                break
    assert diverged  # the Tatkal cache is genuinely a different draw


async def test_get_seat_prediction_is_class_aware_and_deterministic(provider):
    # Find a day where SL and 1A are both waitlisted on the same leg, then assert
    # the AC class is scaled no higher than Sleeper (SL >= 1A) at equal seed.
    found = False
    for day in range(1, 40):
        date = dt.date(2026, 7, day)
        sl_status = await provider.get_seat_status("12345", "A", "D", date, TravelClass.SL)
        ac_status = await provider.get_seat_status("12345", "A", "D", date, TravelClass.AC1)
        if parse_availability(sl_status).status is not AvailabilityStatus.WAITLIST:
            continue
        if parse_availability(ac_status).status is not AvailabilityStatus.WAITLIST:
            continue
        sl_pred = await provider.get_seat_prediction("12345", "A", "D", date, TravelClass.SL)
        ac_pred = await provider.get_seat_prediction("12345", "A", "D", date, TravelClass.AC1)
        if sl_pred is None or ac_pred is None:
            continue
        assert sl_pred >= ac_pred
        # deterministic
        assert sl_pred == await provider.get_seat_prediction("12345", "A", "D", date, TravelClass.SL)
        found = True
        break
    assert found, "no day with both SL and 1A waitlisted + estimated"


async def test_get_seat_prediction_none_for_non_waitlist(provider):
    # AVAILABLE / RAC carry no graded estimate in the fake (priors handle them).
    for day in range(1, 40):
        date = dt.date(2026, 7, day)
        status = await provider.get_seat_status("12345", "A", "F", date, TravelClass.SL)
        if parse_availability(status).status is AvailabilityStatus.AVAILABLE:
            assert await provider.get_seat_prediction("12345", "A", "F", date, TravelClass.SL) is None
            return
    pytest.skip("no AVAILABLE draw in range")


async def test_search_trains_between_offers_carry_prediction(provider):
    raws = await provider.search_trains_between("A", "D", DATE)
    offers = raws[0].general_offers
    assert offers  # the leg yields per-class offers
    # Each offer's prediction_pct is None-or-int AND matches the provider's own
    # get_seat_prediction for that class — verifies the wiring, not just the attr.
    for o in offers:
        assert o.prediction_pct is None or isinstance(o.prediction_pct, int)
        expected = await provider.get_seat_prediction("12345", "A", "D", DATE, o.travel_class)
        assert o.prediction_pct == expected
