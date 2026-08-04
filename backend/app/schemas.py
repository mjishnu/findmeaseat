"""All Pydantic models and enums shared across layers."""

import datetime as dt
from enum import Enum, IntEnum

from pydantic import BaseModel, Field


class Station(BaseModel):
    """A railway station in the autocomplete directory (static local data)."""

    code: str
    name: str
    city: str


class StationStop(BaseModel):
    code: str
    name: str
    distance_km: int = Field(
        ge=0, description="Cumulative distance from the train's origin"
    )


class TrainRoute(BaseModel):
    train_number: str
    train_name: str
    stations: list[StationStop]


class AvailabilityStatus(IntEnum):
    NOT_BOOKABLE = 0
    UNKNOWN = 1
    WAITLIST = 2
    RAC = 3
    AVAILABLE = 4


class BookingQuota(str, Enum):
    """The quota a ticket is booked UNDER. GN and TQ come bundled in one confirmtkt
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

    SL = "SL"  # Sleeper
    AC3 = "3A"  # AC 3-tier
    AC3_ECONOMY = "3E"  # AC 3-tier Economy
    AC2 = "2A"  # AC 2-tier
    AC1 = "1A"  # AC First Class
    CC = "CC"  # AC Chair Car
    EXEC_CHAIR = "EC"  # Executive Chair Car
    SECOND_SITTING = "2S"  # Second Sitting
    FIRST_CLASS = "FC"  # First Class (non-AC)


class RecommendationNoteCode(IntEnum):
    QUOTA_TATKAL = 1
    QUOTA_LADIES = 2
    QUOTA_SENIOR = 3
    BOARDING_CHANGE = 4
    EXTRA_FARE = 5
    ALIGHT_CHANGE = 6
    MISSING_PREDICTION = 7
    PARTIAL_COVERAGE = 8


class ParsedAvailability(BaseModel):
    raw: str
    status: AvailabilityStatus


# --- Train search (between stations) -------------------------------------------
# Provider-internal: raw availability strings, pre-normalization. The service runs
# each through the parser + ranking to build the public ClassAvailability below.
class RawClassOffer(BaseModel):
    travel_class: TravelClass
    raw_availability: str
    fare: int | None = None
    prediction_pct: int | None = (
        None  # confirmtkt predictionPercentage; 0 is real, None = absent
    )


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
    probability: float  # -1 when confirmtkt gives no estimate for this leg
    fare: int | None = None  # None when unpriced/unavailable (0 -> None)


class TrainBetween(BaseModel):
    train_number: str
    train_name: str
    from_code: str
    from_name: str
    to_code: str
    to_name: str
    departure_time: str  # "HH:MM"
    arrival_time: str  # "HH:MM"
    duration_min: int | None = None
    running_days: str  # "1111111" (Mon→Sun)
    has_pantry: bool = False
    distance_km: int | None = None
    general: list[ClassAvailability]
    tatkal: list[ClassAvailability]  # often [] for distant dates (Tatkal window)
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
    availability: ParsedAvailability
    probability: float  # -1 when confirmtkt gives no estimate (ranked last, flagged)
    extra_km: int
    fare: int | None  # None when the upstream did not price this class on this leg
    extra_fare: int | None  # difference vs the direct fare; None if either is unknown
    coverage_pct: float = 1.0  # fraction of user's leg this pair covers (1.0 = full)
    notes: list[
        RecommendationNoteCode
    ]  # semantic note codes; frontend renders the copy


class SwitchAlternative(BaseModel):
    """A different (class, quota) cell whose confirmation chance is strictly
    better than the searched cell — surfaced so the user can switch class, quota,
    or both. Spans the full (class × quota) grid, all from cached pair responses."""

    travel_class: TravelClass
    quota: BookingQuota
    availability: ParsedAvailability
    probability: float  # always set in practice; -1 = no estimate
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
    pairs_skipped: int = (
        0  # covering pairs dropped because the upstream failed for them
    )
    recommendations: list[Recommendation]
    # Other (class, quota) cells with a better confirmation chance for the same
    # leg; empty when the searched cell is already the best available.
    alternatives: list[SwitchAlternative] = []
    partial: bool = False  # echoes whether partial-coverage mode was active
    min_coverage_pct: float = 1.0  # echoes the minimum coverage filter value


# --- Manifest & Fetch Schemas --------------------------------------------------

class FetchDescriptor(BaseModel):
    url: str
    headers: dict[str, str]
    fetch_id: str
    method: str = "GET"
    body: str | None = None


class ManifestResponse(BaseModel):
    """Returned by /manifest AND by /process when more fetches are needed."""
    manifest_id: str
    fetches: list[FetchDescriptor]


class FetchResult(BaseModel):
    fetch_id: str
    status: int       # HTTP status the browser got
    body: str         # raw response text


class ProcessRequest(BaseModel):
    manifest_id: str
    results: list[FetchResult]


class RouteManifestRequest(BaseModel):
    train_number: str = Field(pattern=r"^\d{5}$")


class SeatFinderManifestRequest(BaseModel):
    train_number: str = Field(pattern=r"^\d{5}$")
    user_source: str = Field(min_length=1, max_length=5)
    user_destination: str = Field(min_length=1, max_length=5)
    date: dt.date
    travel_class: TravelClass = TravelClass.SL
    quota: BookingQuota = BookingQuota.GENERAL
    partial: bool = False
    min_coverage_pct: float = Field(default=0.5, ge=0.0, le=1.0)
    require_connect: bool = True


class TrainSearchManifestRequest(BaseModel):
    source: str = Field(min_length=1, max_length=5)
    destination: str = Field(min_length=1, max_length=5)
    date: dt.date


class QuotaSearchManifestRequest(BaseModel):
    source: str = Field(min_length=1, max_length=5)
    destination: str = Field(min_length=1, max_length=5)
    date: dt.date
    quota: BookingQuota
