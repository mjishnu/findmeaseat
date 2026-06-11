import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import ProviderDep
from app.exceptions import TrainNotFoundError
from app.schemas import RecommendationResponse, TrainRoute
from app.services.recommendations import RecommendationService

router = APIRouter(prefix="/api")


@router.get("/find-optimal-route", response_model=RecommendationResponse)
def find_optimal_route(
    provider: ProviderDep,
    train_number: Annotated[str, Query(pattern=r"^\d{5}$", description="5-digit train number")],
    user_source: Annotated[str, Query(min_length=1, max_length=5)],
    user_destination: Annotated[str, Query(min_length=1, max_length=5)],
    date: dt.date,  # FastAPI coerces YYYY-MM-DD and 422s on malformed/impossible dates
) -> RecommendationResponse:
    return RecommendationService(provider).find_optimal_route(
        train_number, user_source, user_destination, date
    )


@router.get("/trains/{train_number}", response_model=TrainRoute)
def get_train(train_number: str, provider: ProviderDep) -> TrainRoute:
    """Route lookup for UI dropdowns."""
    route = provider.get_route(train_number)
    if route is None:
        raise TrainNotFoundError(train_number)
    return route
