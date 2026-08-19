from fastapi import APIRouter

from app.routers.common import GzipRoute
from app.schemas import (
    ManifestResponse,
    ProcessRequest,
    RecommendationResponse,
    SeatFinderManifestRequest,
)
from app.services import seat_finder as seat_finder_service

router = APIRouter(route_class=GzipRoute)


@router.post("/manifest", response_model=ManifestResponse | RecommendationResponse)
async def seat_finder_manifest(body: SeatFinderManifestRequest):
    return await seat_finder_service.create_manifest(
        train_number=body.train_number,
        user_source=body.user_source,
        user_destination=body.user_destination,
        date=body.date,
        travel_class=body.travel_class,
        quota=body.quota,
        partial=body.partial,
        min_coverage_pct=body.min_coverage_pct,
        require_connect=body.require_connect,
    )


@router.post("/process", response_model=ManifestResponse | RecommendationResponse)
async def seat_finder_process(body: ProcessRequest):
    return await seat_finder_service.process_manifest(
        body.manifest_id, body.results
    )
