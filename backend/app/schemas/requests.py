"""API request schemas (inbound validation)."""

import datetime as dt

from pydantic import BaseModel, Field

from app.schemas.enums import BookingQuota, TravelClass


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
    quota: BookingQuota = BookingQuota.GENERAL
