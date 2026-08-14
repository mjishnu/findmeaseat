from fastapi import APIRouter, HTTPException

from app.core.manifest_store import ManifestCache, RouteManifestEntry
from app.core.redis import RouteCache
from app.exceptions import ProviderUnavailableError, TrainNotFoundError
from app.providers.irctc.client import (
    build_erail_header_descriptor,
    build_erail_route_descriptor,
    parse_erail_header,
    parse_erail_route,
)
from app.routers.common import GzipRoute
from app.schemas import (
    ManifestResponse,
    ProcessRequest,
    RouteManifestRequest,
    StationStop,
    TrainRoute,
)

router = APIRouter(route_class=GzipRoute)


@router.post("/manifest", response_model=ManifestResponse | TrainRoute)
async def route_manifest(body: RouteManifestRequest):
    cached = await RouteCache.get(body.train_number)
    if cached:
        return cached

    entry = RouteManifestEntry(train_number=body.train_number)
    mid = ManifestCache.put(entry)
    return ManifestResponse(
        manifest_id=mid, fetches=[build_erail_header_descriptor(body.train_number)]
    )


@router.post("/process", response_model=ManifestResponse | TrainRoute)
async def route_process(body: ProcessRequest):
    entry = ManifestCache.pop(body.manifest_id)
    if not isinstance(entry, RouteManifestEntry):
        raise HTTPException(404, "Manifest expired or unknown")

    if not body.results:
        raise HTTPException(400, "Missing results")
    result = body.results[0]

    if entry.phase == "header":
        parsed = parse_erail_header(result.body)
        if parsed is None:
            raise TrainNotFoundError(entry.train_number)
        entry.train_id, entry.train_name = parsed
        entry.phase = "route"
        mid = ManifestCache.put(entry)
        return ManifestResponse(
            manifest_id=mid, fetches=[build_erail_route_descriptor(entry.train_id)]
        )

    elif entry.phase == "route":
        stops = parse_erail_route(result.body)
        if not stops:
            raise ProviderUnavailableError(
                "erail TRAINROUTE returned no parseable stops"
            )
        route = TrainRoute(
            train_number=entry.train_number,
            train_name=entry.train_name or "",
            stations=[StationStop(**s) for s in stops],
        )
        await RouteCache.put(entry.train_number, route)
        return route
