"""Enums shared across all layers."""

from enum import Enum, IntEnum


class AvailabilityStatus(IntEnum):
    NOT_BOOKABLE = 0
    UNKNOWN = 1
    WAITLIST = 2
    RAC = 3
    AVAILABLE = 4


class BookingQuota(str, Enum):
    GENERAL = "GN"
    TATKAL = "TQ"
    LADIES = "LD"
    SENIOR = "SS"

    @property
    def fetch_group(self) -> str | None:
        """
        Whether to fetch the GN/Tatkal (None) or Ladies/Senior (BookingQuota)
        """
        if self in (BookingQuota.LADIES, BookingQuota.SENIOR):
            return self.value
        return None


class TravelClass(str, Enum):
    SL = "SL"
    AC3 = "3A"
    AC3_ECONOMY = "3E"
    AC2 = "2A"
    AC1 = "1A"
    CC = "CC"
    EXEC_CHAIR = "EC"
    SECOND_SITTING = "2S"
    FIRST_CLASS = "FC"


class RecommendationNoteCode(IntEnum):
    QUOTA_TATKAL = 1
    QUOTA_LADIES = 2
    QUOTA_SENIOR = 3
    BOARDING_CHANGE = 4
    EXTRA_FARE = 5
    ALIGHT_CHANGE = 6
    MISSING_PREDICTION = 7
    PARTIAL_COVERAGE = 8
