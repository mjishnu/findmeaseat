"""All Pydantic models and enums shared across layers."""
import datetime as dt
from enum import Enum

from pydantic import BaseModel, Field


class StationStop(BaseModel):
    code: str
    name: str
    distance_km: int = Field(ge=0, description="Cumulative distance from the train's origin")


class TrainRoute(BaseModel):
    train_number: str
    train_name: str
    stations: list[StationStop]


class AvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    RAC = "RAC"
    WAITLIST = "WAITLIST"
    NOT_BOOKABLE = "NOT_BOOKABLE"  # REGRET / NOT AVAILABLE / DEPARTED / CANCELLED / CHARTING DONE
    UNKNOWN = "UNKNOWN"


class Quota(str, Enum):
    GNWL = "GNWL"  # general — origin-controlled, best clearance odds
    RLWL = "RLWL"  # remote location
    RSWL = "RSWL"  # roadside
    PQWL = "PQWL"  # pooled — shared by many intermediate pairs
    TQWL = "TQWL"  # tatkal — cleared after GNWL at charting
    RQWL = "RQWL"  # request — last resort


class ParsedAvailability(BaseModel):
    raw: str
    status: AvailabilityStatus
    quota: Quota | None = None
    seats: int | None = None
    # For RAC strings the same two slots hold the RAC positions.
    series_wl: int | None = None   # first number: booking-time serial position
    current_wl: int | None = None  # second number: current queue position — drives ranking

    @property
    def label(self) -> str:
        if self.status is AvailabilityStatus.AVAILABLE:
            return f"AVAILABLE ({self.seats} seats)" if self.seats else "AVAILABLE"
        if self.status is AvailabilityStatus.RAC:
            return f"RAC {self.current_wl}" if self.current_wl else "RAC"
        if self.status is AvailabilityStatus.WAITLIST and self.quota:
            return f"{self.quota.value} {self.current_wl}"
        return self.raw


class UserLeg(BaseModel):
    source: str
    destination: str
    distance_km: int
    fare: int
    availability: ParsedAvailability | None = None


class Recommendation(BaseModel):
    rank: int
    book_from: str
    book_to: str
    board_at: str
    alight_at: str
    action: str
    availability: ParsedAvailability
    probability: float
    score: float
    booked_distance_km: int
    extra_km: int
    fare: int
    extra_fare: int
    requires_boarding_change: bool
    notes: list[str]


class RecommendationResponse(BaseModel):
    train_number: str
    train_name: str
    journey_date: dt.date
    user_leg: UserLeg
    pairs_evaluated: int
    recommendations: list[Recommendation]
