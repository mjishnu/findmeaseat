from typing import Annotated

from fastapi import APIRouter, Query

from app.routers.common import DecompressRoute
from app.schemas import Station
from app.services.stations import search_stations as find_stations

router = APIRouter(route_class=DecompressRoute)


@router.get("/stations", response_model=list[Station])
def search_stations(
    q: Annotated[
        str, Query(min_length=1, max_length=40, description="Name, city, or code")
    ],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> list[Station]:
    """Autocomplete suggestions from the bundled station directory."""
    return find_stations(q, limit)
