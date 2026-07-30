# Client-Side Fetch Manifest — Full Architecture

ALL external HTTP calls (erail **and** confirmtkt) go through the user's browser.
The server only parses, validates, and processes. No server-side HTTP client to
external services.

---

## Problem

The live provider (`providers/irctc/`) makes all outbound calls to erail.in and
confirmtkt from the backend's single IP. Under concurrent user load every request
shares that IP, making rate-limiting a single point of failure for the whole app.

## Solution: Browser-Side Fetching via Continuation Manifests

Every feature follows the same flow. The `/process` endpoint can return **either**
more fetches (continuation) **or** the final result:

```
POST /api/<feature>/manifest  { params }
  ← { manifest_id, fetches: [{ url, headers, fetch_id }] }

Browser fetches all URLs concurrently → raw responses

POST /api/<feature>/process  { manifest_id, results: [{ fetch_id, status, body }] }
  ← EITHER { manifest_id, fetches: [...] }   ← continuation: more fetches needed
  ← OR     FinalResponseType                  ← done
```

The frontend discriminates by checking `'fetches' in response && response.fetches.length > 0`.
If true → fetch those URLs and call `/process` again. If false → it's the final result.

### Why continuation is needed

erail's route fetch is **two sequential calls** where step 2 depends on step 1's
parsed result:

1. `GET erail.in/rail/getTrains.aspx?TrainNo=12345` → tilde-delimited text → extract `train_id`
2. `GET erail.in/data.aspx?Action=TRAINROUTE&Data1={train_id}` → tilde-delimited text → extract stops

The browser can't parse tilde-delimited text, so the server must parse step 1
before it can construct step 2's URL. This requires a round-trip back to the
server between the two browser fetches.

**CORS:** Both erail.in and confirmtkt have been verified by the user to not block browser fetches via CORS.

---

## Endpoint Map

| Old Endpoint | New Manifest Pair | Steps |
|---|---|---|
| `GET /api/find-optimal-route` | **DELETE** (replaced by seat-finder) | — |
| `GET /api/trains/{train_number}` | `POST /api/route/manifest` + `/process` | 0–2 (cached → 0; erail header → route → done) |
| *(new)* seat finder | `POST /api/seat-finder/manifest` + `/process` | 0–3 (all cached → 0; erail → route → confirmtkt → done) |
| `GET /api/trains-between` | `POST /api/trains-between/manifest` + `/process` | 0–1 (cached → 0; confirmtkt → done) |
| `GET /api/trains-between/quota` | `POST /api/trains-between/quota/manifest` + `/process` | 0–1 (cached → 0; confirmtkt → done) |
| `GET /api/stations` | **UNCHANGED** (local data, no external calls) | — |

---

## Server-Side Caches (60s TTL)

Two lightweight caches for **parsed** data. Not HTTP caches — they store the
result of parsing browser-fetched responses. Avoids redundant browser round-trips
when the same data is requested multiple times within 60s.

### Route Cache

Stores parsed `TrainRoute` objects keyed by train number. Common hit: SearchForm
fetches route for dropdowns, then seat-finder requests the same train → cache hit
skips both erail phases.

```python
# core/route_cache.py
_cache: dict[str, tuple[float, TrainRoute]] = {}
_TTL = 60.0
_MAX_SIZE = 256

def get(train_number: str) -> TrainRoute | None:
    entry = _cache.get(train_number)
    if entry and time.monotonic() - entry[0] < _TTL:
        return entry[1]
    _cache.pop(train_number, None)
    return None

def put(train_number: str, route: TrainRoute) -> None:
    _cache[train_number] = (time.monotonic(), route)
    if len(_cache) > _MAX_SIZE:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        del _cache[oldest]
```

### Segment Cache

Stores parsed confirmtkt `trainList` arrays keyed by `(source, dest, date, fetch_group)`.
Same key shape as the old `IRCTCClient._segment_cache`. `fetch_group` is `None`
for GN/TQ (bundled), or `"LD"`/`"SS"` for quota searches.

Common hits:
- Seat finder: covering pairs overlap across searches for the same train/date
- Train search → seat finder: the direct (source, dest) pair is already cached
- Re-searches within 60s skip all browser fetches

```python
# core/segment_cache.py
_cache: dict[tuple[str, str, str, str | None], tuple[float, list[dict]]] = {}
_TTL = 60.0
_MAX_SIZE = 512

def get(source: str, dest: str, date_str: str, fetch_group: str | None) -> list[dict] | None:
    key = (source, dest, date_str, fetch_group)
    entry = _cache.get(key)
    if entry and time.monotonic() - entry[0] < _TTL:
        return entry[1]
    _cache.pop(key, None)
    return None

def put(source: str, dest: str, date_str: str, fetch_group: str | None, train_list: list[dict]) -> None:
    key = (source, dest, date_str, fetch_group)
    _cache[key] = (time.monotonic(), train_list)
    if len(_cache) > _MAX_SIZE:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        del _cache[oldest]
```

### How caching affects continuation steps

When ALL required data is cached, the `/manifest` endpoint returns the **final
result directly** (no fetches needed, 0 continuation steps). When SOME data is
cached, only non-cached segments are included in the fetches list. The manifest
entry stores cached segments so the process endpoint can merge them with
browser-fetched results.

---

## Architecture Changes

### New: Shared schemas (additions to `schemas.py`)

```python
class FetchDescriptor(BaseModel):
    url: str
    headers: dict[str, str]
    fetch_id: str

class ManifestResponse(BaseModel):
    """Returned by /manifest AND by /process when more fetches are needed."""
    manifest_id: str
    fetches: list[FetchDescriptor]

class FetchResult(BaseModel):
    fetch_id: str
    status: int       # HTTP status the browser got
    body: str         # raw response text

class ProcessRequest(BaseModel):
    manifest_id: str
    results: list[FetchResult]
```

### New: Per-feature request schemas (additions to `schemas.py`)

```python
class RouteManifestRequest(BaseModel):
    train_number: str = Field(pattern=r"^\d{5}$")

class SeatFinderManifestRequest(BaseModel):
    train_number: str = Field(pattern=r"^\d{5}$")
    user_source: str = Field(min_length=1, max_length=5)
    user_destination: str = Field(min_length=1, max_length=5)
    date: dt.date
    travel_class: TravelClass = TravelClass.SL
    quota: BookingQuota = BookingQuota.GENERAL

class TrainSearchManifestRequest(BaseModel):
    source: str = Field(min_length=1, max_length=5)
    destination: str = Field(min_length=1, max_length=5)
    date: dt.date

class QuotaSearchManifestRequest(BaseModel):
    source: str = Field(min_length=1, max_length=5)
    destination: str = Field(min_length=1, max_length=5)
    date: dt.date
    quota: BookingQuota
```

### New: `ManifestStore` (in-memory, TTL + size-bounded)

Single store for all manifest entry types. Plain `dict`, no lock needed (put/pop
are synchronous dict ops with no `await` in between — no interleaving risk in
async Python).

```python
# core/manifest_store.py
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
```

### New: `PreFetchedProvider`

Implements `RailDataProvider` Protocol. Reads from pre-parsed `trainList` dicts
(populated from browser-fetched JSON AND/OR segment cache). Makes zero outbound
calls. Reuses `irctc_client` parsing helpers (`find_train`, `class_cache`,
`_to_int`, `cache_key`).

```python
# providers/prefetched/provider.py
class PreFetchedProvider:
    """RailDataProvider that reads from pre-parsed confirmtkt trainList dicts.
    Data may come from browser fetches, segment cache, or both."""

    def __init__(
        self,
        entry: SeatFinderEntry,
        parsed_segments: dict[str, list[dict]],  # fetch_id -> trainList
    ) -> None:
        self._entry = entry
        self._parsed = parsed_segments

    async def get_route(self, train_number: str) -> TrainRoute | None:
        return self._entry.route

    async def get_seat_status(self, train_number, source, destination,
                               journey_date, travel_class,
                               quota=BookingQuota.GENERAL) -> str:
        fid = f"{source}|{destination}"
        train = find_train(self._parsed.get(fid, []), train_number)
        if train is None:
            return "NOT AVAILABLE"
        # Must read availabilityDisplayName — NOT availability — matching
        # the live provider's get_seat_status (provider.py:153).
        display = class_cache(train, travel_class.value, quota).get(
            "availabilityDisplayName"
        )
        return display or "NOT AVAILABLE"

    async def get_fare(self, train_number, source, destination,
                        journey_date, travel_class,
                        quota=BookingQuota.GENERAL) -> int | None:
        fid = f"{source}|{destination}"
        train = find_train(self._parsed.get(fid, []), train_number)
        if train is None:
            return None
        # Use .get() not [] to avoid KeyError; or None coerces 0 → None
        # matching the live provider (provider.py:178–183).
        return _to_int(class_cache(train, travel_class.value, quota).get("fare")) or None

    async def get_seat_prediction(self, train_number, source, destination,
                                    journey_date, travel_class,
                                    quota=BookingQuota.GENERAL) -> int | None:
        fid = f"{source}|{destination}"
        train = find_train(self._parsed.get(fid, []), train_number)
        if train is None:
            return None
        return _to_int(class_cache(train, travel_class.value, quota).get("predictionPercentage"))

    async def get_train_classes(self, train_number, source, destination,
                                 journey_date,
                                 quota=BookingQuota.GENERAL) -> list[str]:
        # The blob has ALL classes the train offers (not just the searched class).
        # Returning real codes lets RecommendationService._build_better_alternatives
        # work naturally — "switch to 3A" banners come for free.
        fid = f"{source}|{destination}"
        train = find_train(self._parsed.get(fid, []), train_number)
        if train is None:
            return []
        cache = train.get(cache_key(quota)) or {}
        return [code for code, entry in cache.items()
                if isinstance(entry, dict) and entry.get("availabilityDisplayName")]

    # search_trains_between / search_quota_availability → raise NotImplementedError
    # (manifest path only; these methods are removed from the Protocol anyway)
```

---

## Parsing Helpers (refactored from `providers/irctc/client.py`)

The `IRCTCClient` **class** is deleted entirely (HTTP client, caches, semaphore,
retry logic — all gone since the browser handles fetching). Module-level functions
stay in `client.py`:

**Kept:** `_clean`, `_to_int`, `_NUM_RE`, `find_train`, `cache_key`, `class_cache`,
`format_date`, `ERAIL_GET_TRAINS`, `ERAIL_DATA`, `CONFIRMTKT_SEARCH`.

**New** (extracted from `_fetch_route_uncached`):
```python
def parse_erail_header(body: str) -> tuple[str, str, str] | None:
    """Parse erail getTrains response → (train_id, train_no, train_name),
    or None if train not found."""
    if "train not found" in body.lower():
        return None
    segs = body.split("~~~~~~~~")
    d1 = _clean(segs[0])
    if len(d1[1]) > 6:
        d1 = d1[1:]
    d2 = _clean(segs[1])
    return d2[12], d1[1].replace("^", ""), d1[2]

def parse_erail_route(route_text: str) -> list[dict[str, Any]]:
    """Parse erail TRAINROUTE response → list of {code, name, distance_km}."""
    stops = []
    for item in route_text.split("~^"):
        det = _clean(item)
        if len(det) < 10:
            continue
        distance = _to_int(det[6])
        if distance is None:
            continue
        stops.append({"code": det[1], "name": det[2], "distance_km": distance})
    return stops
```

**New** URL builder functions:
```python
_BROWSER_HEADERS: dict[str, str] = {} # Browser will automatically set User-Agent

def build_erail_header_descriptor(train_number: str) -> FetchDescriptor:
    params = urlencode({"TrainNo": train_number, "DataSource": 0, "Language": 0, "Cache": "true"})
    return FetchDescriptor(url=f"{ERAIL_GET_TRAINS}?{params}",
                           headers=_BROWSER_HEADERS, fetch_id="erail_header")

def build_erail_route_descriptor(train_id: str) -> FetchDescriptor:
    params = urlencode({"Action": "TRAINROUTE", "Password": 2012,
                        "Data1": train_id, "Data2": 0, "Cache": "true"})
    return FetchDescriptor(url=f"{ERAIL_DATA}?{params}",
                           headers=_BROWSER_HEADERS, fetch_id="erail_route")

def build_confirmtkt_descriptor(
    source: str, destination: str, date: dt.date, quota: BookingQuota, fetch_id: str,
) -> FetchDescriptor:
    params = {
        "sourceStationCode": source, "destinationStationCode": destination,
        "dateOfJourney": format_date(date), "addAvailabilityCache": "true",
        "excludeMultiTicketAlternates": "false", "excludeBoostAlternates": "false",
        "sortBy": "DEFAULT", "enableNearby": "true", "enableTG": "true",
        "tGPlan": "CTG-3", "showTGPrediction": "false",
        "tgColor": "DEFAULT", "showPredictionGlobal": "true",
    }
    # quota= param is required for LD/SS; GN/TQ are bundled without it.
    if quota in (BookingQuota.LADIES, BookingQuota.SENIOR):
        params["quota"] = quota.value
    return FetchDescriptor(url=f"{CONFIRMTKT_SEARCH}?{urlencode(params)}",
                           headers=_BROWSER_HEADERS, fetch_id=fetch_id)
```

**Kept in `provider.py`** (module-level functions; `IRCTCRailDataProvider` class deleted):
`build_raw_trains_between`, `build_quota_rows`, `_offers`, `_UNBOOKABLE`.

---

## Endpoint Details

### 1. Route Lookup: `POST /api/route/manifest` + `/process`

**Manifest:**
```python
@router.post("/route/manifest")
async def route_manifest(body: RouteManifestRequest, store: ManifestStoreDep):
    cached = route_cache.get(body.train_number)
    if cached:
        return cached  # Return TrainRoute directly — 0 fetches

    entry = RouteManifestEntry(train_number=body.train_number)
    mid = store.put(entry)
    return ManifestResponse(manifest_id=mid,
                            fetches=[build_erail_header_descriptor(body.train_number)])
```

**Process** (handles both erail phases):
```python
@router.post("/route/process")
async def route_process(body: ProcessRequest, store: ManifestStoreDep):
    entry = store.pop(body.manifest_id)
    if not isinstance(entry, RouteManifestEntry):
        raise HTTPException(404, "Manifest expired or unknown")
    result = body.results[0]

    if entry.phase == "header":
        parsed = parse_erail_header(result.body)
        if parsed is None:
            raise TrainNotFoundError(entry.train_number)
        train_id, train_no, train_name = parsed
        entry.phase = "route"
        entry.train_id = train_id
        entry.train_no = train_no
        entry.train_name = train_name
        mid = store.put(entry)
        return ManifestResponse(manifest_id=mid,
                                fetches=[build_erail_route_descriptor(train_id)])

    elif entry.phase == "route":
        stops = parse_erail_route(result.body)
        if not stops:
            raise ProviderUnavailableError("erail TRAINROUTE returned no parseable stops")
        route = TrainRoute(train_number=entry.train_number, train_name=entry.train_name,
                           stations=[StationStop(**s) for s in stops])
        route_cache.put(entry.train_number, route)
        return route  # Final result — done
```

The response is a **union**: `ManifestResponse` (continuation) or `TrainRoute` (done).
FastAPI handles this with `response_model=ManifestResponse | TrainRoute`.
The frontend discriminates via `'fetches' in response`.

---

### 2. Seat Finder: `POST /api/seat-finder/manifest` + `/process`

**Manifest** (skips erail if route cached; skips confirmtkt pairs if segment cached):
```python
@router.post("/seat-finder/manifest")
async def seat_finder_manifest(body: SeatFinderManifestRequest, store: ManifestStoreDep):
    validate_journey_date(body.date)
    source = body.user_source.strip().upper()
    destination = body.user_destination.strip().upper()

    cached_route = route_cache.get(body.train_number)
    if cached_route:
        # Skip erail — build confirmtkt manifest (with segment cache awareness)
        pairs = enumerate_covering_pairs(cached_route, source, destination)
        fetch_group = body.quota.value if body.quota in (BookingQuota.LADIES, BookingQuota.SENIOR) else None
        date_str = format_date(body.date)
        cached_segs: dict[str, list[dict]] = {}
        fetches: list[FetchDescriptor] = []
        fetch_id_to_pair = {}
        for b, a in pairs:
            fid = f"{b.code}|{a.code}"
            fetch_id_to_pair[fid] = (b, a)
            hit = segment_cache.get(b.code, a.code, date_str, fetch_group)
            if hit is not None:
                cached_segs[fid] = hit
            else:
                fetches.append(build_confirmtkt_descriptor(
                    b.code, a.code, body.date, body.quota, fid))

        entry = SeatFinderEntry(
            phase="fetch", route=cached_route, pairs=pairs,
            fetch_id_to_pair=fetch_id_to_pair, cached_segments=cached_segs or None,
            train_number=body.train_number, user_source=source,
            user_destination=destination, journey_date=body.date,
            travel_class=body.travel_class, quota=body.quota,
        )

        if not fetches:
            # ALL pairs segment-cached — process directly, 0 fetches
            provider = PreFetchedProvider(entry, cached_segs)
            return await RecommendationService(provider).find_optimal_route(
                cached_route.train_number, source, destination,
                body.date, body.travel_class, body.quota)

        mid = store.put(entry)
        return ManifestResponse(manifest_id=mid, fetches=fetches)

    # No cached route — start with erail
    entry = SeatFinderEntry(
        phase="header", train_number=body.train_number,
        user_source=source, user_destination=destination,
        journey_date=body.date, travel_class=body.travel_class, quota=body.quota,
    )
    mid = store.put(entry)
    return ManifestResponse(manifest_id=mid,
                            fetches=[build_erail_header_descriptor(body.train_number)])
```

**Process** (3 phases: header → route → fetch):
```python
@router.post("/seat-finder/process")
async def seat_finder_process(body: ProcessRequest, store: ManifestStoreDep):
    entry = store.pop(body.manifest_id)
    if not isinstance(entry, SeatFinderEntry):
        raise HTTPException(404, "Manifest expired or unknown")

    if entry.phase == "header":
        parsed = parse_erail_header(body.results[0].body)
        if parsed is None:
            raise TrainNotFoundError(entry.train_number)
        entry.train_id, entry.train_no, entry.train_name = parsed
        entry.phase = "route"
        mid = store.put(entry)
        return ManifestResponse(manifest_id=mid,
                                fetches=[build_erail_route_descriptor(entry.train_id)])

    elif entry.phase == "route":
        stops = parse_erail_route(body.results[0].body)
        if not stops:
            raise ProviderUnavailableError("erail TRAINROUTE returned no parseable stops")
        route = TrainRoute(train_number=entry.train_number, train_name=entry.train_name,
                           stations=[StationStop(**s) for s in stops])
        route_cache.put(entry.train_number, route)
        pairs = enumerate_covering_pairs(route, entry.user_source, entry.user_destination)
        fetch_group = entry.quota.value if entry.quota in (BookingQuota.LADIES, BookingQuota.SENIOR) else None
        date_str = format_date(entry.journey_date)

        cached_segs: dict[str, list[dict]] = {}
        fetches: list[FetchDescriptor] = []
        fetch_id_to_pair = {}
        for b, a in pairs:
            fid = f"{b.code}|{a.code}"
            fetch_id_to_pair[fid] = (b, a)
            hit = segment_cache.get(b.code, a.code, date_str, fetch_group)
            if hit is not None:
                cached_segs[fid] = hit
            else:
                fetches.append(build_confirmtkt_descriptor(
                    b.code, a.code, entry.journey_date, entry.quota, fid))

        entry.route = route
        entry.pairs = pairs
        entry.fetch_id_to_pair = fetch_id_to_pair
        entry.cached_segments = cached_segs or None

        if not fetches:
            # All segment-cached after route phase
            provider = PreFetchedProvider(entry, cached_segs)
            return await RecommendationService(provider).find_optimal_route(
                route.train_number, entry.user_source, entry.user_destination,
                entry.journey_date, entry.travel_class, entry.quota)

        entry.phase = "fetch"
        mid = store.put(entry)
        return ManifestResponse(manifest_id=mid, fetches=fetches)

    elif entry.phase == "fetch":
        # Validate: no duplicates, no unknown fetch_ids (missing OK → skipped pairs)
        submitted_ids = [r.fetch_id for r in body.results]
        if len(submitted_ids) != len(set(submitted_ids)):
            raise HTTPException(400, "Duplicate fetch_id")
        if not set(submitted_ids) <= set(entry.fetch_id_to_pair.keys()):
            raise HTTPException(400, "Unknown fetch_id")

        # Parse browser-fetched JSON into trainList dicts
        fetch_group = entry.quota.value if entry.quota in (BookingQuota.LADIES, BookingQuota.SENIOR) else None
        date_str = format_date(entry.journey_date)
        parsed_segments: dict[str, list[dict]] = {}
        for r in body.results:
            train_list: list[dict] = []
            if r.status == 200 and r.body:
                try:
                    payload = json.loads(r.body)
                    data = payload.get("data") if isinstance(payload, dict) else None
                    train_list = (data or {}).get("trainList", []) if isinstance(data, dict) else []
                except (json.JSONDecodeError, AttributeError):
                    pass
            parsed_segments[r.fetch_id] = train_list
            # Cache for future requests
            if train_list:
                board, alight = r.fetch_id.split("|")
                segment_cache.put(board, alight, date_str, fetch_group, train_list)

        # Merge with segment-cached data
        if entry.cached_segments:
            parsed_segments.update(entry.cached_segments)

        provider = PreFetchedProvider(entry, parsed_segments)
        return await RecommendationService(provider).find_optimal_route(
            entry.route.train_number, entry.user_source, entry.user_destination,
            entry.journey_date, entry.travel_class, entry.quota,
        )
```

---

### 3. Train Search: `POST /api/trains-between/manifest` + `/process`

**Manifest:** Check segment cache first. If cached, process directly and return
`TrainsBetweenResponse`. Otherwise, 1 confirmtkt fetch (GN+TQ bundled).

```python
@router.post("/trains-between/manifest")
async def trains_between_manifest(body: TrainSearchManifestRequest, store: ManifestStoreDep):
    validate_journey_date(body.date)
    source = body.source.strip().upper()
    destination = body.destination.strip().upper()
    date_str = format_date(body.date)

    cached = segment_cache.get(source, destination, date_str, None)
    if cached is not None:
        raw_trains = build_raw_trains_between(cached)
        return TrainsBetweenResponse(source=source, destination=destination,
                                      journey_date=body.date,
                                      trains=[to_train_between(t) for t in raw_trains])

    entry = TrainSearchEntry(source=source, destination=destination, journey_date=body.date)
    mid = store.put(entry)
    return ManifestResponse(manifest_id=mid,
                            fetches=[build_confirmtkt_descriptor(
                                source, destination, body.date, BookingQuota.GENERAL, "search")])
```

**Process:** Parse JSON → `build_raw_trains_between` → `to_train_between` each →
return `TrainsBetweenResponse`. Cache the parsed trainList.

`TrainSearchService` class is removed; `_to_train_between` and `_to_class` become
module-level functions `to_train_between` and `to_class` (they're pure transformations
that don't use `self._provider`).

---

### 4. Quota Search: `POST /api/trains-between/quota/manifest` + `/process`

**Manifest:** Check segment cache (keyed with `fetch_group = quota.value`). If
cached, process directly. Otherwise, 1 confirmtkt fetch with `quota=LD|SS`.

**Process:** Parse JSON → `build_quota_rows` → return `TrainsQuotaAvailabilityResponse`.
Cache the parsed trainList.

---

## RailDataProvider Protocol (slimmed)

Remove `search_trains_between` and `search_quota_availability` — no provider
implements them anymore. Keep only the methods `RecommendationService` calls:

```python
class RailDataProvider(Protocol):
    async def get_route(self, train_number: str) -> TrainRoute | None: ...
    async def get_seat_status(self, train_number, source, destination,
                               journey_date, travel_class, quota=...) -> str: ...
    async def get_seat_prediction(self, ...) -> int | None: ...
    async def get_fare(self, ...) -> int | None: ...
    async def get_train_classes(self, ...) -> list[str]: ...
```

---

## Frontend Changes

### Generic `executeManifest` helper (in `client.ts`)

```typescript
async function postRequest<T>(url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const err: unknown = await res.json()
      if (typeof err === 'object' && err !== null && 'detail' in err && typeof err.detail === 'string')
        detail = err.detail
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

async function fetchWithRetry(
  f: FetchDescriptor, signal?: AbortSignal, retries = 3,
): Promise<FetchResult> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      if (attempt > 0) await new Promise(r => setTimeout(r, 500 * attempt))
      const res = await fetch(f.url, { headers: f.headers, signal })
      return { fetch_id: f.fetch_id, status: res.status, body: await res.text() }
    } catch {
      if (attempt === retries) break
    }
  }
  return { fetch_id: f.fetch_id, status: 0, body: '' }
}

function isContinue(r: unknown): r is ManifestResponse {
  return typeof r === 'object' && r !== null && 'fetches' in r &&
    Array.isArray((r as Record<string, unknown>).fetches) &&
    ((r as Record<string, unknown>).fetches as unknown[]).length > 0
}

async function executeManifest<T>(
  manifestUrl: string, processUrl: string, body: unknown, signal?: AbortSignal,
): Promise<T> {
  let response: unknown = await postRequest(manifestUrl, body, signal)

  // If manifest returned the final result directly (cached data)
  if (!isContinue(response)) return response as T

  while (true) {
    const manifest = response as ManifestResponse
    const results = await Promise.all(
      manifest.fetches.map(f => fetchWithRetry(f, signal))
    )
    response = await postRequest(processUrl,
      { manifest_id: manifest.manifest_id, results }, signal)
    if (!isContinue(response)) return response as T
  }
}
```

### Updated API functions (same signatures — zero component changes)

```typescript
export interface FetchDescriptor {
  url: string
  headers: Record<string, string>
  fetch_id: string
}

export interface ManifestResponse {
  manifest_id: string
  fetches: FetchDescriptor[]
}

export interface FetchResult {
  fetch_id: string
  status: number
  body: string
}

export function getTrainRoute(trainNumber: string, signal?: AbortSignal): Promise<TrainRoute> {
  return executeManifest('/api/route/manifest', '/api/route/process',
    { train_number: trainNumber }, signal)
}

export function findOptimalRoute(query: SearchQuery, signal?: AbortSignal): Promise<RecommendationResponse> {
  return executeManifest('/api/seat-finder/manifest', '/api/seat-finder/process', {
    train_number: query.trainNumber,
    user_source: query.source,
    user_destination: query.destination,
    date: query.date,
    travel_class: query.travelClass,
    quota: query.quota,
  }, signal)
}

export function searchTrainsBetween(
  source: string, destination: string, date: string, signal?: AbortSignal,
): Promise<TrainsBetweenResponse> {
  return executeManifest('/api/trains-between/manifest', '/api/trains-between/process',
    { source, destination, date }, signal)
}

export function searchTrainsQuotaAvailability(
  source: string, destination: string, date: string, quota: BookingQuota, signal?: AbortSignal,
): Promise<TrainsQuotaAvailabilityResponse> {
  return executeManifest('/api/trains-between/quota/manifest', '/api/trains-between/quota/process',
    { source, destination, date, quota }, signal)
}
```

`SeatFinderPanel.tsx`, `TrainSearchPanel.tsx`, `SearchForm.tsx` all call the same
function signatures — they don't know about manifests. Only change: add 404
handling for expired manifests in `SeatFinderPanel.tsx`:

```typescript
const message =
  err instanceof ApiError
    ? err.status === 404
      ? 'Search expired — please retry'
      : err.message
    : 'Could not reach the server — is the backend running?'
```

The old GET-only `request<T>` helper stays for `searchStations` (local data, no
manifest needed).

---

## What Does NOT Change

- `RecommendationService` — untouched (takes any `RailDataProvider`, gets `PreFetchedProvider`)
- `RecommendationResponse` schema — identical shape, same frontend rendering
- Parser, ranking, pairs, dates — all core logic untouched
- `GET /api/stations` — local data, no external calls
- `App.tsx`, `SearchForm.tsx`, `TrainSearchPanel.tsx` — same API function signatures

---

## Graceful Degradation

- A pair whose browser fetch returned non-200 or unparseable body → parsed as
  empty trainList → `PreFetchedProvider` returns `"NOT AVAILABLE"` for that pair →
  `RecommendationService` treats it as `pairs_skipped` (not fatal).
- If ALL pairs fail → `recommendations` is empty, `pairs_skipped` equals
  `pairs_evaluated` — same UX as today's degradation.
- Missing `fetch_id`s in the submitted results are allowed (the validation only
  rejects unknown/duplicate IDs, not missing ones). Missing pairs become skipped.
- **Expired manifest:** `/process` returns 404. Frontend shows "Search expired —
  please retry" via the `SeatFinderPanel` error handling.

---

## Cleanup Summary

### DELETE entirely
| What | Why |
|---|---|
| `IRCTCClient` class in `client.py` | No server-side HTTP calls |
| `IRCTCRailDataProvider` class in `provider.py` | No server-side provider |
| `get_provider`, `close_provider`, `ProviderDep`, `_build_provider` in `dependencies.py` | No provider singleton |
| `close_provider` call in `main.py` lifespan | Nothing to close |
| `GET /find-optimal-route` in `routes.py` | Replaced by seat-finder manifest |
| `GET /trains/{train_number}` in `routes.py` | Replaced by route manifest |
| `GET /trains-between` in `routes.py` | Replaced by train search manifest |
| `GET /trains-between/quota` in `routes.py` | Replaced by quota manifest |
| `TrainSearchService` class in `train_search.py` | `_to_train_between` + `_to_class` become module-level functions |
| `search_trains_between`, `search_quota_availability` from `RailDataProvider` | No provider implements them |

### KEEP (module-level functions / constants)
| What | Where |
|---|---|
| `_clean`, `_to_int`, `_NUM_RE`, `find_train`, `cache_key`, `class_cache`, `format_date`, URL constants | `client.py` |
| `build_raw_trains_between`, `build_quota_rows`, `_offers`, `_UNBOOKABLE` | `provider.py` |
| `parse_availability` | `parser.py` |
| `enumerate_covering_pairs` | `pairs.py` |
| `confirmation_probability`, `option_score` | `ranking.py` |
| `validate_journey_date` | `dates.py` |
| `RecommendationService` class | `recommendations.py` (untouched) |
| `RailDataProvider` Protocol (slimmed) | `base.py` |

---

## File Changelist

| File | Change |
|---|---|
| `backend/app/schemas.py` | Add `FetchDescriptor`, `ManifestResponse`, `ProcessRequest`, `FetchResult`, `RouteManifestRequest`, `SeatFinderManifestRequest`, `TrainSearchManifestRequest`, `QuotaSearchManifestRequest` |
| `backend/app/core/manifest_store.py` | **[NEW]** `ManifestEntry` + `RouteManifestEntry` + `SeatFinderEntry` + `TrainSearchEntry` + `ManifestStore` |
| `backend/app/core/route_cache.py` | **[NEW]** 60s TTL route cache (`get`/`put`) |
| `backend/app/core/segment_cache.py` | **[NEW]** 60s TTL segment cache (`get`/`put`) |
| `backend/app/providers/irctc/client.py` | **DELETE** `IRCTCClient` class. **ADD** `parse_erail_header`, `parse_erail_route`, URL builder functions. Keep module-level helpers |
| `backend/app/providers/irctc/provider.py` | **DELETE** `IRCTCRailDataProvider` class. Keep `build_raw_trains_between`, `build_quota_rows`, `_offers`, `_UNBOOKABLE` |
| `backend/app/providers/irctc/__init__.py` | Remove `IRCTCRailDataProvider` export |
| `backend/app/providers/prefetched/__init__.py` | **[NEW]** |
| `backend/app/providers/prefetched/provider.py` | **[NEW]** `PreFetchedProvider` |
| `backend/app/providers/base.py` | Remove `search_trains_between`, `search_quota_availability` from Protocol |
| `backend/app/dependencies.py` | **DELETE** `get_provider`, `close_provider`, `ProviderDep`. **ADD** `ManifestStoreDep` |
| `backend/app/routers/routes.py` | **DELETE** all 4 GET endpoints. **ADD** 8 POST endpoints. Keep `GET /stations` |
| `backend/app/services/train_search.py` | **DELETE** `TrainSearchService` class. **ADD** module-level `to_train_between`, `to_class` |
| `backend/app/main.py` | Remove `close_provider` import and lifespan call |
| `frontend/src/api/client.ts` | **ADD** `postRequest`, `fetchWithRetry`, `isContinue`, `executeManifest`, manifest types. **REPLACE** 4 API functions. Keep `request` for stations |
| `frontend/src/components/SeatFinderPanel.tsx` | Add 404 "expired" handling in catch block |

Files UNCHANGED: `parser.py`, `pairs.py`, `ranking.py`, `dates.py`,
`recommendations.py`, `stations.py`, `exceptions.py`, `App.tsx`, `SearchForm.tsx`,
`TrainSearchPanel.tsx`, all other components.

---

## Implementation Tasks

- [ ] **Task 1 — Schemas** — Add all new Pydantic models to `schemas.py`
- [ ] **Task 2 — Caches + Store** — Create `core/manifest_store.py`, `core/route_cache.py`, `core/segment_cache.py`
- [ ] **Task 3 — Parsing Helpers + URL Builders** — Refactor `client.py`: delete `IRCTCClient` class, add erail parsers and URL builders
- [ ] **Task 4 — Provider Cleanup** — Delete `IRCTCRailDataProvider` from `provider.py`, slim `base.py` Protocol, refactor `train_search.py` to module-level functions
- [ ] **Task 5 — PreFetchedProvider** — Create `providers/prefetched/provider.py`
- [ ] **Task 6 — Dependencies** — Rewrite `dependencies.py` (remove provider, add ManifestStoreDep), update `main.py`
- [ ] **Task 7 — Routes** — Rewrite `routes.py` with all 8 manifest/process endpoints + stations
- [ ] **Task 8 — Frontend** — Update `client.ts` with `executeManifest` pattern, update `SeatFinderPanel.tsx` error handling

---

## Verification

1. Start backend (`uvicorn app.main:app`) + frontend (`npm run dev`)
2. **Route lookup**: Enter a train number in SearchForm → DevTools shows
   `POST /api/route/manifest` → browser fetches 2 erail URLs sequentially →
   `POST /api/route/process` (×2) → station dropdowns populate
3. **Seat finder**: Click search → erail + confirmtkt fetch chain → recommendations
4. **Cached route**: Same train within 60s → manifest skips erail (1 step not 3)
5. **Cached segments**: Same search within 60s → manifest returns final result
   directly (0 steps — no browser fetches at all)
6. **Train search**: Switch tab → `POST /api/trains-between/manifest` → 1 confirmtkt
   fetch → results appear
7. **Expired manifest**: Wait >2 min → 404 → "Search expired" message
