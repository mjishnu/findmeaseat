"""API response schemas (outbound serialization)."""

import datetime as dt

from pydantic import BaseModel

from app.schemas.domain import ClassAvailability, ParsedAvailability, TrainIdentity
from app.schemas.enums import (
    BookingQuota,
    RecommendationNoteCode,
    TravelClass,
)


class TrainBetween(TrainIdentity):
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
    general: list[ClassAvailability] = []
    tatkal: list[ClassAvailability] = []
    classes: list[ClassAvailability] = []


class TrainsBetweenResponse(BaseModel):
    source: str
    destination: str
    journey_date: dt.date
    trains: list[TrainBetween]


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
