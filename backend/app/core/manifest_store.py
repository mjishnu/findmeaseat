import time
from uuid import uuid4
from dataclasses import dataclass, field
import datetime as dt

from app.schemas import TrainRoute, StationStop, TravelClass, BookingQuota

@dataclass
class ManifestEntry:
    created_at: float = 0.0

# --- Route lookup ---
@dataclass
class RouteManifestEntry(ManifestEntry):
    phase: str = "header"          # "header" → "route"
    train_number: str = ""
    train_id: str | None = None    # set after header phase
    train_no: str | None = None
    train_name: str | None = None

# --- Seat finder ---
@dataclass
class SeatFinderEntry(ManifestEntry):
    phase: str = "header"          # "header" → "route" → "fetch"
    train_number: str = ""
    user_source: str = ""
    user_destination: str = ""
    journey_date: dt.date = field(default_factory=dt.date.today)
    travel_class: TravelClass = TravelClass.SL
    quota: BookingQuota = BookingQuota.GENERAL
    # Partial-coverage controls
    partial: bool = False
    min_coverage_pct: float = 1.0
    require_connect: bool = True
    # Set after header phase
    train_id: str | None = None
    train_no: str | None = None
    train_name: str | None = None
    # Set after route phase
    route: TrainRoute | None = None
    pairs: list[tuple[StationStop, StationStop]] | None = None
    fetch_id_to_pair: dict[str, tuple[StationStop, StationStop]] | None = None
    # Segment-cached confirmtkt data for pairs that didn't need browser fetching
    cached_segments: dict[str, list[dict]] | None = None
    # Set after fetch phase — carried into verify phase
    verify_candidates: list[dict] | None = None
    verify_alternatives: list[dict] | None = None
    verify_context: dict | None = None

# --- Train search (general + quota) ---
@dataclass
class TrainSearchEntry(ManifestEntry):
    source: str = ""
    destination: str = ""
    journey_date: dt.date = field(default_factory=dt.date.today)
    quota: BookingQuota | None = None  # None for general, set for LD/SS

class ManifestStore:
    def __init__(self, ttl: float = 120.0, max_size: int = 1024):
        self._store: dict[str, ManifestEntry] = {}
        self._ttl = ttl
        self._max_size = max_size

    def put(self, entry: ManifestEntry) -> str:
        now = time.monotonic()
        self._store = {k: v for k, v in self._store.items() if now - v.created_at < self._ttl}
        if len(self._store) >= self._max_size:
            oldest = min(self._store, key=lambda k: self._store[k].created_at)
            del self._store[oldest]
        mid = uuid4().hex[:16]
        entry.created_at = now
        self._store[mid] = entry
        return mid

    def pop(self, manifest_id: str) -> ManifestEntry | None:
        entry = self._store.pop(manifest_id, None)
        if entry is None:
            return None
        if time.monotonic() - entry.created_at > self._ttl:
            return None
        return entry
