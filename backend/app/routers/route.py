from fastapi import APIRouter

from app.routers.common import GzipRoute
from app.schemas import (
    ManifestResponse,
    ProcessRequest,
    RouteManifestRequest,
    TrainRoute,
)
from app.services import route as route_service

router = APIRouter(route_class=GzipRoute)


@router.post("/manifest", response_model=ManifestResponse | TrainRoute)
async def route_manifest(body: RouteManifestRequest):
    return await route_service.get_or_create_manifest(body.train_number)


@router.post("/process", response_model=ManifestResponse | TrainRoute)
async def route_process(body: ProcessRequest):
    return await route_service.process_manifest(body.manifest_id, body.results)
