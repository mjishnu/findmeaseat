"""Route lookup service — cache + manifest lifecycle for train route resolution."""

from app.exceptions import (
    InvalidManifestError,
    ManifestExpiredError,
    ProviderUnavailableError,
    TrainNotFoundError,
)
from app.infrastructure.cache import RouteCache
from app.infrastructure.manifest_store import ManifestCache, RouteManifestEntry
from app.providers.prefetched.client import (
    build_erail_header_descriptor,
    build_erail_route_descriptor,
    parse_erail_header,
    parse_erail_route,
)
from app.schemas import (
    FetchResult,
    ManifestResponse,
    StationStop,
    TrainRoute,
    TravelClass,
)


async def get_or_create_manifest(
    train_number: str,
) -> ManifestResponse | TrainRoute:
    """Return cached route, or create a manifest for browser-side fetching."""
    cached = await RouteCache.get(train_number)
    if cached:
        return cached

    entry = RouteManifestEntry(train_number=train_number)
    mid = ManifestCache.put(entry)
    return ManifestResponse(
        manifest_id=mid, fetches=[build_erail_header_descriptor(train_number)]
    )


async def process_manifest(
    manifest_id: str, results: list[FetchResult]
) -> ManifestResponse | TrainRoute:
    """Advance the multi-phase route resolution (header → route → cached)."""
    entry = ManifestCache.pop(manifest_id)
    if not isinstance(entry, RouteManifestEntry):
        raise ManifestExpiredError()

    if not results:
        raise InvalidManifestError("Missing results")

    result = results[0]

    if entry.phase == "header":
        parsed = parse_erail_header(result.body)
        if parsed is None:
            raise TrainNotFoundError(entry.train_number)
        entry.train_id = parsed["train_id"]
        entry.train_name = parsed["train_name"]
        entry.running_days = parsed["running_days"]
        entry.classes = parsed["classes"]
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
        valid_classes: list[TravelClass] = []
        for c in entry.classes:
            try:
                valid_classes.append(TravelClass(c))
            except ValueError:
                pass
        route = TrainRoute(
            train_number=entry.train_number,
            train_name=entry.train_name or "",
            stations=[StationStop(**s) for s in stops],
            running_days=entry.running_days or "1111111",
            classes=valid_classes,
        )
        await RouteCache.put(entry.train_number, route)
        return route
