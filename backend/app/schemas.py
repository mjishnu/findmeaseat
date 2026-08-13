"""All Pydantic models and enums shared across layers."""

import datetime as dt
from dataclasses import dataclass
from enum import Enum, IntEnum

from pydantic import BaseModel, Field


class Station(BaseModel):
    code: str
    name: str
    city: str


class StationStop(BaseModel):
    code: str
    name: str
    distance_km: int = Field(ge=0, description="Cumulative distance from origin")


class TrainIdentity(BaseModel):
    train_number: str
    train_name: str


class TrainRoute(TrainIdentity):
    stations: list[StationStop]


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


class ParsedAvailability(BaseModel):
    raw: str
    status: AvailabilityStatus


@dataclass
class Candidate:
    board: StationStop
    alight: StationStop
    parsed: ParsedAvailability
    probability: float
    extra_km: int
    fare: int
    extra_fare: int
    coverage_pct: float = 1.0
    board_at: str = ""
    alight_at: str = ""


class RawClassOffer(BaseModel):
    travel_class: TravelClass
    raw_availability: str
    fare: int = -1
    prediction_pct: int = -1


class TrainBetweenBase(TrainIdentity):
    from_code: str
    from_name: str
    to_code: str
    to_name: str
    departure_time: str
    arrival_time: str
    duration_min: int = -1
    running_days: str
    has_pantry: bool = False
    distance_km: int = -1
    allowed_quotas: list[str] = []


class RawTrainBetween(TrainBetweenBase):
    general_offers: list[RawClassOffer]
    tatkal_offers: list[RawClassOffer]


class ClassAvailability(BaseModel):
    travel_class: TravelClass
    availability: ParsedAvailability
    probability: float
    fare: int = -1


class TrainBetween(TrainBetweenBase):
    general: list[ClassAvailability]
    tatkal: list[ClassAvailability]


class JourneyContext(BaseModel):
    source: str
    destination: str
    journey_date: dt.date


class TrainsBetweenResponse(JourneyContext):
    trains: list[TrainBetween]


class TrainQuotaClasses(BaseModel):
    train_number: str
    from_code: str
    departure_time: str
    classes: list[ClassAvailability]


class TrainsQuotaAvailabilityResponse(JourneyContext):
    quota: BookingQuota
    trains: list[TrainQuotaClasses]


class UserLeg(BaseModel):
    source: str
    destination: str
    distance_km: int
    fare: int = -1
    availability: ParsedAvailability | None = None


class Recommendation(BaseModel):
    rank: int
    book_from: str
    book_to: str
    board_at: str
    alight_at: str
    availability: ParsedAvailability
    probability: float
    extra_km: int
    fare: int
    extra_fare: int
    coverage_pct: float = 1.0
    notes: list[RecommendationNoteCode]


class SwitchAlternative(ClassAvailability):
    quota: BookingQuota
    fare: int = -1
    fare_delta: int = -1


class RecommendationResponse(BaseModel):
    train_number: str
    train_name: str
    journey_date: dt.date
    travel_class: TravelClass
    quota: BookingQuota
    user_leg: UserLeg
    pairs_evaluated: int
    pairs_skipped: int = 0
    recommendations: list[Recommendation]
    alternatives: list[SwitchAlternative] = []
    partial: bool = False
    min_coverage_pct: float = 1.0


class FetchDescriptor(BaseModel):
    url: str
    headers: dict[str, str]
    fetch_id: str
    method: str = "GET"
    body: str | None = None


class ManifestResponse(BaseModel):
    manifest_id: str
    fetches: list[FetchDescriptor]


class FetchResult(BaseModel):
    fetch_id: str
    status: int
    body: str


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


class StationPairDateRequest(BaseModel):
    source: str = Field(min_length=1, max_length=5)
    destination: str = Field(min_length=1, max_length=5)
    date: dt.date


class TrainSearchManifestRequest(StationPairDateRequest):
    pass


class QuotaSearchManifestRequest(StationPairDateRequest):
    quota: BookingQuota
