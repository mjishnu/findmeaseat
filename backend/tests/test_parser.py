import pytest

from app.core.parser import parse_availability
from app.schemas import AvailabilityStatus as S
from app.schemas import Quota


@pytest.mark.parametrize(
    ("raw", "status", "quota", "seats", "series", "current"),
    [
        # AVAILABLE — IRCTC native (hyphen, zero-padded) and aggregator (spaced) forms
        ("AVAILABLE-0044", S.AVAILABLE, None, 44, None, None),
        ("AVAILABLE 10", S.AVAILABLE, None, 10, None, None),
        ("AVL 44", S.AVAILABLE, None, 44, None, None),
        ("AVAILABLE", S.AVAILABLE, None, None, None, None),
        # Zero seats: quota exists but nothing bookable — never recommend
        ("AVAILABLE-0000", S.NOT_BOOKABLE, None, None, None, None),
        ("AVL 0", S.NOT_BOOKABLE, None, None, None, None),
        # Hybrid: a WL series existed but booking now confirms immediately
        ("WL3/AVAILABLE", S.AVAILABLE, None, None, None, None),
        ("GNWL10/AVAILABLE", S.AVAILABLE, None, None, None, None),
        # Waitlists — spaced and unspaced, all quota types, case-insensitive
        ("GNWL15/WL10", S.WAITLIST, Quota.GNWL, None, 15, 10),
        ("GNWL 15/WL 10", S.WAITLIST, Quota.GNWL, None, 15, 10),
        ("rlwl5/wl2", S.WAITLIST, Quota.RLWL, None, 5, 2),
        ("PQWL 10/WL 8", S.WAITLIST, Quota.PQWL, None, 10, 8),
        ("TQWL4/WL4", S.WAITLIST, Quota.TQWL, None, 4, 4),
        ("WL 7", S.WAITLIST, Quota.GNWL, None, None, 7),  # bare WL ⇒ general series
        ("GNWL-15/WL-10", S.WAITLIST, Quota.GNWL, None, 15, 10),  # hyphenated variant
        # RAC — two-number, single-number, and hyphenated forms
        ("RAC 12/RAC 5", S.RAC, None, None, 12, 5),
        ("RAC7", S.RAC, None, None, None, 7),
        ("RAC-12", S.RAC, None, None, None, 12),
        # Terminal / unbookable states
        ("REGRET", S.NOT_BOOKABLE, None, None, None, None),
        ("REGRET/WL110", S.NOT_BOOKABLE, None, None, None, None),
        ("NOT AVAILABLE", S.NOT_BOOKABLE, None, None, None, None),
        ("TRAIN DEPARTED", S.NOT_BOOKABLE, None, None, None, None),
        ("TRAIN CANCELLED", S.NOT_BOOKABLE, None, None, None, None),
        ("CHARTING DONE", S.NOT_BOOKABLE, None, None, None, None),
        # confirmtkt decorates some availability strings with a trailing "#"
        # marker (seen on live Tatkal data) — tolerate it like any other noise.
        ("AVAILABLE-0072#", S.AVAILABLE, None, 72, None, None),
        ("RLWL58/WL58#", S.WAITLIST, Quota.RLWL, None, 58, 58),
        ("NOT AVAILABLE#", S.NOT_BOOKABLE, None, None, None, None),
        # Garbage
        ("??!", S.UNKNOWN, None, None, None, None),
    ],
)
def test_parse_availability(raw, status, quota, seats, series, current):
    parsed = parse_availability(raw)
    assert parsed.status is status
    assert parsed.quota == quota
    assert parsed.seats == seats
    assert parsed.series_wl == series
    assert parsed.current_wl == current
    assert parsed.raw == raw  # original preserved for display
