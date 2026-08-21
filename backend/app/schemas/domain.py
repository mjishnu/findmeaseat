import datetime as dt
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
    day_offset: int = Field(
        default=0, ge=0, description="Day offset relative to origin (0 = same day)"
    )


class TrainIdentity(BaseModel):
    train_number: str
    train_name: str


class TrainRoute(TrainIdentity):
    stations: list[StationStop]
    running_days: str = "1111111"
    classes: list[TravelClass] = []

    def get_day_offset(self, code: str) -> int:
        """Return the day offset for a station code (0 if not found)."""
        stop = next((s for s in self.stations if s.code == code), None)
        return stop.day_offset if stop else 0

    def boarding_date_for(
        self,
        board: str,
        user_source: str,
        user_date: dt.date,
    ) -> dt.date:
        """Calculate the departure date at a boarding station relative to the user's journey date."""
        board_offset = self.get_day_offset(board)
        user_offset = self.get_day_offset(user_source)
        return user_date + dt.timedelta(days=board_offset - user_offset)


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
