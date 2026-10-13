"""Journey-date rules shared by every search.

IRCTC's booking day is IST (not server-local), and tickets open for a 60-day
advance reservation period. Both the seat-finder and train search validate
against these, so the logic lives here once.
"""
import datetime as dt
from zoneinfo import ZoneInfo

from app.exceptions import InvalidJourneyDateError

ADVANCE_RESERVATION_DAYS = 60  # IRCTC ARP, 60 days excluding journey date (since Nov 2024)
BOOKING_TZ = ZoneInfo("Asia/Kolkata")  # IRCTC's booking day is IST, not server-local
# Most days a train can run past its origin date (the longest, Vivek Express, ends on day 4)
MAX_DAY_OFFSET = 3


def booking_day_today() -> dt.date:
    """Today in the railway's timezone — the anchor for date validation."""
    return dt.datetime.now(BOOKING_TZ).date()


def validate_journey_date(journey_date: dt.date, extra_days: int = 0) -> None:
    """The ARP counts from the train's origin date, so a station `extra_days` into
    the run can be booked that many days past today + ARP."""
    today = booking_day_today()
    if journey_date < today:
        raise InvalidJourneyDateError("Journey date is in the past")
    if journey_date > today + dt.timedelta(days=ADVANCE_RESERVATION_DAYS + extra_days):
        raise InvalidJourneyDateError(
            f"Journey date is outside the {ADVANCE_RESERVATION_DAYS}-day advance reservation period"
        )
