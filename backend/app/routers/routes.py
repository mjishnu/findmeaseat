import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.dependencies import ProviderDep, StationDirectoryDep
from app.exceptions import TrainNotFoundError
from app.schemas import (
    BookingQuota,
    RecommendationResponse,
    Station,
    TrainRoute,
    TrainsBetweenResponse,
    TrainsQuotaAvailabilityResponse,
    TravelClass,
)
from app.services.recommendations import RecommendationService
from app.services.train_search import TrainSearchService

router = APIRouter(prefix="/api")


@router.get("/find-optimal-route", response_model=RecommendationResponse)
async def find_optimal_route(
    provider: ProviderDep,
    train_number: Annotated[str, Query(pattern=r"^\d{5}$", description="5-digit train number")],
    user_source: Annotated[str, Query(min_length=1, max_length=5)],
    user_destination: Annotated[str, Query(min_length=1, max_length=5)],
    date: dt.date,  # FastAPI coerces YYYY-MM-DD and 422s on malformed/impossible dates
    travel_class: TravelClass = TravelClass.SL,  # 422s on an unknown class code
    quota: BookingQuota = BookingQuota.GENERAL,  # GN | TQ | LD | SS; 422s on an unknown code
) -> RecommendationResponse:
    return await RecommendationService(provider).find_optimal_route(
        train_number, user_source, user_destination, date, travel_class, quota
    )


@router.get("/trains/{train_number}", response_model=TrainRoute)
async def get_train(
    provider: ProviderDep,
    train_number: Annotated[str, Path(pattern=r"^\d{5}$", description="5-digit train number")],
) -> TrainRoute:
    """Route lookup for UI dropdowns."""
    route = await provider.get_route(train_number)
    if route is None:
        raise TrainNotFoundError(train_number)
    return route


@router.get("/trains-between", response_model=TrainsBetweenResponse)
async def trains_between(
    provider: ProviderDep,
    source: Annotated[str, Query(min_length=1, max_length=5, description="Source station code")],
    destination: Annotated[str, Query(min_length=1, max_length=5, description="Destination station code")],
    date: dt.date,  # FastAPI coerces YYYY-MM-DD and 422s on malformed/impossible dates
) -> TrainsBetweenResponse:
    """Every train running source→destination on the date, with per-class
    availability + fare for both General and Tatkal quotas."""
    return await TrainSearchService(provider).search(source, destination, date)


@router.get("/trains-between/quota", response_model=TrainsQuotaAvailabilityResponse)
async def trains_between_quota(
    provider: ProviderDep,
    source: Annotated[str, Query(min_length=1, max_length=5, description="Source station code")],
    destination: Annotated[str, Query(min_length=1, max_length=5, description="Destination station code")],
    date: dt.date,
    quota: BookingQuota,  # LD | SS (GN/TQ arrive in /trains-between); 422s on unknown
) -> TrainsQuotaAvailabilityResponse:
    """One quota's per-class availability for every train on the leg — the lazy
    fetch for Ladies/Senior, which aren't in the bundled /trains-between response."""
    return await TrainSearchService(provider).search_quota(source, destination, date, quota)


@router.get("/stations", response_model=list[Station])
def search_stations(
    directory: StationDirectoryDep,
    q: Annotated[str, Query(min_length=1, max_length=40, description="Name, city, or code")],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> list[Station]:
    """Autocomplete suggestions from the bundled station directory."""
    return directory.search(q, limit)
