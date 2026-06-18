"""All Pydantic models and enums shared across layers."""
import datetime as dt
from enum import Enum

from pydantic import BaseModel, Field


class Station(BaseModel):
    """A railway station in the autocomplete directory (static local data)."""
    code: str
    name: str
    city: str


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


class BookingQuota(str, Enum):
    """The quota a ticket is booked UNDER — distinct from `Quota` above, which
    names a waitlist *type* (GNWL/RLWL/…). GN and TQ come bundled in one confirmtkt
    response (`availabilityCache` / `availabilityCacheTatkal`), so reading the other
    costs no extra call. LD and SS each require a separate `quota=`-parameterised
    confirmtkt call that fills `availabilityCacheForQuota`. Values are confirmtkt's
    own quota codes."""

    GENERAL = "GN"
    TATKAL = "TQ"
    LADIES = "LD"
    SENIOR = "SS"


class TravelClass(str, Enum):
    """IRCTC reservation classes. Values are the codes IRCTC/confirmtkt use,
    so they pass straight to the provider and into query strings unchanged.
    Member names avoid leading digits (not legal Python identifiers)."""

    SL = "SL"              # Sleeper
    AC3 = "3A"             # AC 3-tier
    AC3_ECONOMY = "3E"     # AC 3-tier Economy
    AC2 = "2A"             # AC 2-tier
    AC1 = "1A"             # AC First Class
    CC = "CC"              # AC Chair Car
    EXEC_CHAIR = "EC"      # Executive Chair Car
    SECOND_SITTING = "2S"  # Second Sitting
    FIRST_CLASS = "FC"     # First Class (non-AC)


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


# --- Train search (between stations) -------------------------------------------
# Provider-internal: raw availability strings, pre-normalization. The service runs
# each through the parser + ranking to build the public ClassAvailability below.
class RawClassOffer(BaseModel):
    travel_class: TravelClass
    raw_availability: str
    fare: int | None = None
    prediction_pct: int | None = None  # confirmtkt predictionPercentage; 0 is real, None = absent


class RawTrainBetween(BaseModel):
    train_number: str
    train_name: str
    from_code: str
    from_name: str
    to_code: str
    to_name: str
    departure_time: str
    arrival_time: str
    duration_min: int | None = None
    running_days: str
    has_pantry: bool = False
    distance_km: int | None = None
    general_offers: list[RawClassOffer]
    tatkal_offers: list[RawClassOffer]
    allowed_quotas: list[str] = []


class ClassAvailability(BaseModel):
    travel_class: TravelClass
    availability: ParsedAvailability
    probability: float | None  # None when confirmtkt gives no estimate for this leg
    fare: int | None = None  # None when unpriced/unavailable (0 -> None)


class TrainBetween(BaseModel):
    train_number: str
    train_name: str
    from_code: str
    from_name: str
    to_code: str
    to_name: str
    departure_time: str   # "HH:MM"
    arrival_time: str     # "HH:MM"
    duration_min: int | None = None
    running_days: str     # "1111111" (Mon→Sun)
    has_pantry: bool = False
    distance_km: int | None = None
    general: list[ClassAvailability]
    tatkal: list[ClassAvailability]   # often [] for distant dates (Tatkal window)
    allowed_quotas: list[str] = []


class TrainsBetweenResponse(BaseModel):
    source: str
    destination: str
    journey_date: dt.date
    trains: list[TrainBetween]


class TrainQuotaClasses(BaseModel):
    """One train's per-class availability under a single quota. Carries the card's
    disambiguators — train_number is NOT unique within a result (enableNearby)."""
    train_number: str
    from_code: str
    departure_time: str
    classes: list[ClassAvailability]


class TrainsQuotaAvailabilityResponse(BaseModel):
    source: str
    destination: str
    journey_date: dt.date
    quota: BookingQuota
    trains: list[TrainQuotaClasses]


class UserLeg(BaseModel):
    source: str
    destination: str
    distance_km: int
    fare: int | None = None  # None when the class isn't priced/offered on this leg
    availability: ParsedAvailability | None = None


class Recommendation(BaseModel):
    rank: int
    book_from: str
    book_to: str
    board_at: str
    alight_at: str
    action: str
    availability: ParsedAvailability
    probability: float | None  # None when confirmtkt gives no estimate (ranked last, flagged)
    score: float | None        # None mirrors a None probability
    booked_distance_km: int
    extra_km: int
    fare: int | None  # None when the upstream did not price this class on this leg
    extra_fare: int | None  # difference vs the direct fare; None if either is unknown
    requires_boarding_change: bool
    notes: list[str]


class SwitchAlternative(BaseModel):
    """A different (class, quota) cell whose confirmation chance is strictly
    better than the searched cell — surfaced so the user can switch class, quota,
    or both. Spans the full (class × quota) grid, all from cached pair responses."""
    travel_class: TravelClass
    quota: BookingQuota
    availability: ParsedAvailability
    probability: float | None  # always set in practice; widened for consistency
    fare: int | None = None
    fare_delta: int | None = None  # vs the searched (class, quota) direct-leg fare


class RecommendationResponse(BaseModel):
    train_number: str
    train_name: str
    journey_date: dt.date
    travel_class: TravelClass
    quota: BookingQuota  # echoes the searched booking quota
    user_leg: UserLeg
    pairs_evaluated: int
    pairs_skipped: int = 0  # covering pairs dropped because the upstream failed for them
    recommendations: list[Recommendation]
    # Other (class, quota) cells with a better confirmation chance for the same
    # leg; empty when the searched cell is already the best available.
    alternatives: list[SwitchAlternative] = []
