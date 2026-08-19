"""Train search service — cache + manifest lifecycle for trains-between queries."""

import datetime as dt

from app.domain.dates import validate_journey_date
from app.exceptions import InvalidManifestError, ManifestExpiredError
from app.infrastructure.cache import FullSearchCache, SegmentCache
from app.infrastructure.manifest_store import ManifestCache, TrainSearchEntry
from app.providers.prefetched.client import build_confirmtkt_descriptor, format_date
from app.providers.prefetched.parser import extract_json_data
from app.providers.prefetched.transforms import build_trains_between
from app.schemas import (
    FetchResult,
    ManifestResponse,
    TrainsBetweenResponse,
)
from app.schemas.enums import BookingQuota


async def get_or_create_manifest(
    source: str,
    destination: str,
    date: dt.date,
    quota: BookingQuota,
) -> ManifestResponse | TrainsBetweenResponse:
    """Return cached search results, or create a manifest for browser-side fetching."""
    validate_journey_date(date)
    source = source.strip().upper()
    destination = destination.strip().upper()
    date_str = format_date(date)
    fetch_group = quota.fetch_group

    if await FullSearchCache.get(source, destination, date_str, fetch_group):
        cached = await SegmentCache.get_all(source, destination, date_str, fetch_group)
        if cached:
            return TrainsBetweenResponse(
                source=source,
                destination=destination,
                journey_date=date,
                trains=build_trains_between(cached),
            )

    entry = TrainSearchEntry(
        source=source, destination=destination, journey_date=date, quota=quota
    )
    mid = ManifestCache.put(entry)
    return ManifestResponse(
        manifest_id=mid,
        fetches=[
            build_confirmtkt_descriptor(source, destination, date, quota, "search")
        ],
    )


async def process_manifest(
    manifest_id: str, results: list[FetchResult]
) -> TrainsBetweenResponse:
    """Process browser-fetched confirmtkt results, cache them, and return response."""
    entry = ManifestCache.pop(manifest_id)
    if not isinstance(entry, TrainSearchEntry):
        raise ManifestExpiredError()

    if not results:
        raise InvalidManifestError("Missing results")

    r = results[0]
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
            date_str = format_date(entry.journey_date)
            await SegmentCache.put_many(
                entry.source,
                entry.destination,
                date_str,
                fetch_group,
                mapping,
            )
            await FullSearchCache.put(
                entry.source,
                entry.destination,
                date_str,
                fetch_group,
            )

    return TrainsBetweenResponse(
        source=entry.source,
        destination=entry.destination,
        journey_date=entry.journey_date,
        trains=build_trains_between(train_list),
    )
