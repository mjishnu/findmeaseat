from fastapi import APIRouter

from app.routers.common import GzipRoute
from app.routers.route import router as route_router
from app.routers.seat_finder import router as seat_finder_router
from app.routers.stations import router as stations_router
from app.routers.train_search import router as train_search_router

api_router = APIRouter(prefix="/api", route_class=GzipRoute)

api_router.include_router(route_router, prefix="/route", tags=["route"])
api_router.include_router(
    seat_finder_router, prefix="/seat-finder", tags=["seat-finder"]
)
api_router.include_router(
    train_search_router, prefix="/trains-between", tags=["train-search"]
)
api_router.include_router(stations_router, tags=["stations"])

__all__ = ["api_router"]
