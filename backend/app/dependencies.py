from typing import Annotated

from fastapi import Depends

from app.providers.base import RailDataProvider
from app.providers.irctc import IRCTCRailDataProvider
from app.services.stations import StationDirectory

_provider: RailDataProvider | None = None
_station_directory: StationDirectory | None = None


def _build_provider() -> RailDataProvider:
    """THE swap point. The live IRCTC provider (erail.in + confirmtkt) is the
    only data source. To add another (a different scraper, an official API, a
    DB), implement the RailDataProvider Protocol and return it here."""
    return IRCTCRailDataProvider()


def get_provider() -> RailDataProvider:
    global _provider
    if _provider is None:
        _provider = _build_provider()
    return _provider


async def close_provider() -> None:
    """Release the provider's HTTP client on shutdown."""
    global _provider
    if _provider is not None:
        aclose = getattr(_provider, "aclose", None)
        if aclose is not None:
            await aclose()
        _provider = None


ProviderDep = Annotated[RailDataProvider, Depends(get_provider)]


def get_station_directory() -> StationDirectory:
    """The in-memory station autocomplete directory, loaded once from the bundled
    dataset (static local data — not a RailDataProvider concern)."""
    global _station_directory
    if _station_directory is None:
        _station_directory = StationDirectory.from_json()
    return _station_directory


StationDirectoryDep = Annotated[StationDirectory, Depends(get_station_directory)]
