from fastapi import APIRouter, HTTPException

from app.core.dates import validate_journey_date
from app.core.manifest_store import ManifestCache, TrainSearchEntry
from app.core.parser import extract_json_data
from app.core.redis import SegmentCache
from app.providers.irctc.client import build_confirmtkt_descriptor, format_date
from app.providers.irctc.provider import build_trains_between
from app.routers.common import GzipRoute
from app.schemas import (
    ManifestResponse,
    ProcessRequest,
    TrainsBetweenResponse,
    TrainSearchManifestRequest,
)

router = APIRouter(route_class=GzipRoute)


@router.post("/manifest", response_model=ManifestResponse | TrainsBetweenResponse)
async def trains_between_manifest(body: TrainSearchManifestRequest):
    validate_journey_date(body.date)
    source = body.source.strip().upper()
    destination = body.destination.strip().upper()
    date_str = format_date(body.date)
    fetch_group = body.quota.fetch_group

    cached = await SegmentCache.get_all(source, destination, date_str, fetch_group)
    if cached:
        return TrainsBetweenResponse(
            source=source,
            destination=destination,
            journey_date=body.date,
            trains=build_trains_between(cached),
        )

    entry = TrainSearchEntry(
        source=source, destination=destination, journey_date=body.date, quota=body.quota
    )
    mid = ManifestCache.put(entry)
    return ManifestResponse(
        manifest_id=mid,
        fetches=[
            build_confirmtkt_descriptor(
                source, destination, body.date, body.quota, "search"
            )
        ],
    )


@router.post("/process", response_model=TrainsBetweenResponse)
async def trains_between_process(body: ProcessRequest):
    entry = ManifestCache.pop(body.manifest_id)
    if not isinstance(entry, TrainSearchEntry):
        raise HTTPException(404, "Manifest expired or unknown")

    if not body.results:
        raise HTTPException(400, "Missing results")

    r = body.results[0]
    train_list: list[dict] = []
    if r.status == 200 and r.body:
        data = extract_json_data(r.body)
        if data:
            train_list = data.get("trainList", [])

    fetch_group = entry.quota.fetch_group

    if train_list:
        mapping = {
            str(t["trainNumber"]): t
            for t in train_list
            if isinstance(t, dict) and "trainNumber" in t
        }
        if mapping:
            await SegmentCache.put_many(
                entry.source,
                entry.destination,
                format_date(entry.journey_date),
                fetch_group,
                mapping,
            )

    return TrainsBetweenResponse(
        source=entry.source,
        destination=entry.destination,
        journey_date=entry.journey_date,
        trains=build_trains_between(train_list),
    )
