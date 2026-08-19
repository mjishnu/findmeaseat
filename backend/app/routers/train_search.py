from fastapi import APIRouter

from app.routers.common import DecompressRoute
from app.schemas import (
    ManifestResponse,
    ProcessRequest,
    TrainsBetweenResponse,
    TrainSearchManifestRequest,
)
from app.services import train_search as train_search_service

router = APIRouter(route_class=DecompressRoute)


@router.post("/manifest", response_model=ManifestResponse | TrainsBetweenResponse)
async def trains_between_manifest(body: TrainSearchManifestRequest):
    return await train_search_service.get_or_create_manifest(
        body.source, body.destination, body.date, body.quota
    )


@router.post("/process", response_model=TrainsBetweenResponse)
async def trains_between_process(body: ProcessRequest):
    return await train_search_service.process_manifest(
        body.manifest_id, body.results
    )
