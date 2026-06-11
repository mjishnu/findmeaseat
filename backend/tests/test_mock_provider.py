import datetime as dt

import pytest

from app.core.parser import parse_availability
from app.providers.mock.fixtures import calculate_fare
from app.providers.mock.provider import MockRailDataProvider
from app.schemas import AvailabilityStatus, Quota

DATE = dt.date(2026, 7, 1)


@pytest.fixture()
def provider() -> MockRailDataProvider:
    return MockRailDataProvider()


def test_route_lookup(provider):
    route = provider.get_route("12345")
    assert route is not None
    assert [s.code for s in route.stations] == ["A", "B", "C", "D", "E", "F"]
    assert provider.get_route("99999") is None


def test_seat_status_is_deterministic(provider):
    first = provider.get_seat_status("12345", "C", "D", DATE)
    second = provider.get_seat_status("12345", "C", "D", DATE)
    assert first == second


def test_seat_status_is_always_parseable(provider):
    codes = ["A", "B", "C", "D", "E", "F"]
    for i, src in enumerate(codes):
        for dst in codes[i + 1 :]:
            parsed = parse_availability(provider.get_seat_status("12345", src, dst, DATE))
            assert parsed.status is not AvailabilityStatus.UNKNOWN


def test_quota_mirrors_real_mechanics(provider):
    """Origin pairs draw GNWL; remote-location/terminus pairs RLWL; the rest PQWL."""
    for day in range(1, 15):  # several dates so we hit WAITLIST draws, not just AVAILABLE
        date = dt.date(2026, 7, day)
        for src, dst, expected in [
            ("A", "D", Quota.GNWL),   # from origin
            ("B", "F", Quota.RLWL),   # to terminus
            ("C", "D", Quota.RLWL),   # D is a remote-location station
            ("B", "C", Quota.PQWL),   # intermediate → intermediate
        ]:
            parsed = parse_availability(provider.get_seat_status("12345", src, dst, date))
            if parsed.status is AvailabilityStatus.WAITLIST:
                assert parsed.quota == expected, f"{src}->{dst} on {date}"


def test_fare_is_telescopic_rounded_and_floored():
    assert calculate_fare(40) == max(105, 5 * round(40 * 1.30 / 5))  # no rebate band
    assert calculate_fare(10) == 105                                  # class minimum
    assert calculate_fare(170) == 190                                 # 170·1.30·0.85 ≈ 187.9 → 190
    assert calculate_fare(1020) < calculate_fare(510) * 2             # concave: long legs cheaper per km
    fares = [calculate_fare(km) for km in (50, 120, 310, 480, 750, 1020)]
    assert fares == sorted(fares)                                     # monotonic
    assert all(f % 5 == 0 for f in fares)                             # rounded to ₹5


def test_fare_provider_uses_route_distance(provider):
    assert provider.get_fare("12345", "C", "D") == calculate_fare(170)  # 480 − 310
