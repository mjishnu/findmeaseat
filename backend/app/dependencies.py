from typing import Annotated
from fastapi import Depends

from app.core.manifest_store import ManifestStore
from app.services.stations import StationDirectory

_manifest_store: ManifestStore | None = None
_station_directory: StationDirectory | None = None


def get_manifest_store() -> ManifestStore:
    global _manifest_store
    if _manifest_store is None:
        _manifest_store = ManifestStore()
    return _manifest_store


ManifestStoreDep = Annotated[ManifestStore, Depends(get_manifest_store)]


def get_station_directory() -> StationDirectory:
    """The in-memory station autocomplete directory, loaded once from the bundled
    dataset (static local data — not a RailDataProvider concern)."""
    global _station_directory
    if _station_directory is None:
        _station_directory = StationDirectory.from_json()
    return _station_directory


StationDirectoryDep = Annotated[StationDirectory, Depends(get_station_directory)]
