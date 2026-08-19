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


def booking_day_today() -> dt.date:
    """Today in the railway's timezone — the anchor for date validation."""
    return dt.datetime.now(BOOKING_TZ).date()


def validate_journey_date(journey_date: dt.date) -> None:
    today = booking_day_today()
    if journey_date < today:
        raise InvalidJourneyDateError("Journey date is in the past")
    if journey_date > today + dt.timedelta(days=ADVANCE_RESERVATION_DAYS):
        raise InvalidJourneyDateError(
            f"Journey date is outside the {ADVANCE_RESERVATION_DAYS}-day advance reservation period"
        )
