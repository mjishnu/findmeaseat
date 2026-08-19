"""Domain value objects and internal data models."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.schemas.enums import AvailabilityStatus, TravelClass


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


class ClassAvailability(BaseModel):
    travel_class: TravelClass
    availability: ParsedAvailability
    probability: float
    fare: int = -1
