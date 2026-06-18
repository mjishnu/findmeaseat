# Ladies & Senior-Citizen Quotas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Ladies (LD) and Senior-Citizen (SS) quota availability to both the Seat Finder and Train Search, alongside the existing General (GN) and Tatkal (TQ).

**Architecture:** confirmtkt's existing `/trains/search` endpoint returns LD/SS per-class availability under `availabilityCacheForQuota` when called with a `quota=` param (identical field shape to today's GN/TQ caches, so the existing parser/ranking are reused). GN/TQ stay bundled in the first call; LD/SS are fetched lazily per quota and cached. The quota picker becomes a `<select>` dropdown on both forms.

**Tech Stack:** Backend — FastAPI, Pydantic v2, httpx, pytest (`asyncio_mode=auto`). Frontend — React 18 + TypeScript + Vite + Tailwind (no test harness).

## Global Constraints

- **Quota set:** `GN` General, `TQ` Tatkal, `LD` Ladies, `SS` Senior Citizen. Premium Tatkal is NOT available from confirmtkt — do not add it.
- **UI labels:** exactly `General`, `Tatkal`, `Ladies`, `Senior Citizen`.
- **confirmtkt cache keys:** GN→`availabilityCache`, TQ→`availabilityCacheTatkal`, LD/SS→`availabilityCacheForQuota`.
- **Backend commands run from `backend/`** using the project venv, e.g. `.venv/Scripts/python.exe -m pytest tests/... -v` (PowerShell: `.\.venv\Scripts\python.exe`). There is **no type checker** in CI — annotations are documentation only.
- **Frontend commands run from `frontend/`**: verify with `npx tsc --noEmit` and `npm run build`. There is no frontend test runner — correctness is verified by typecheck + build (+ manual check in the running app).
- **client.ts mirrors schemas.py by hand** — keep the two in sync.
- **The live IRCTC provider is the only data source.** Tests use `httpx.MockTransport` (client layer) or the test doubles in `tests/conftest.py` / `tests/fakes.py`.
- **Every commit message ends with** the trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: Quota enum + cache routing + docstrings

**Files:**
- Modify: `backend/app/schemas.py` (BookingQuota enum + docstring)
- Modify: `backend/app/providers/irctc/client.py` (`cache_key`)
- Modify: `backend/app/providers/base.py` (Protocol docstring)
- Test: `backend/tests/test_irctc_provider.py`

**Interfaces:**
- Produces: `BookingQuota.LADIES = "LD"`, `BookingQuota.SENIOR = "SS"`; `cache_key(BookingQuota.LADIES) == "availabilityCacheForQuota"`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_irctc_provider.py` (near `test_class_cache_selects_quota_specific_cache`, line ~411):

```python
_TRAIN_ALL_QUOTAS = {
    "trainNumber": "12951",
    "availabilityCache": {"SL": {"availabilityDisplayName": "AVAILABLE-0042"}},
    "availabilityCacheTatkal": {"SL": {"availabilityDisplayName": "WL5/WL2"}},
    "availabilityCacheForQuota": {"SL": {"availabilityDisplayName": "LADIES WL3"}},
}


def test_class_cache_routes_ladies_and_senior_to_for_quota_cache():
    train = _TRAIN_ALL_QUOTAS
    assert class_cache(train, "SL", BookingQuota.GENERAL).get("availabilityDisplayName") == "AVAILABLE-0042"
    assert class_cache(train, "SL", BookingQuota.TATKAL).get("availabilityDisplayName") == "WL5/WL2"
    assert class_cache(train, "SL", BookingQuota.LADIES).get("availabilityDisplayName") == "LADIES WL3"
    assert class_cache(train, "SL", BookingQuota.SENIOR).get("availabilityDisplayName") == "LADIES WL3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_irctc_provider.py::test_class_cache_routes_ladies_and_senior_to_for_quota_cache -v`
Expected: FAIL — `AttributeError: LADIES` (enum member doesn't exist).

- [ ] **Step 3a: Add the enum members + fix the docstring**

In `backend/app/schemas.py`, replace the `BookingQuota` class (lines ~44-51):

```python
class BookingQuota(str, Enum):
    """The quota a ticket is booked UNDER — distinct from `Quota` above, which
    names a waitlist *type* (GNWL/RLWL/…). GN and TQ come bundled in one confirmtkt
    response (`availabilityCache` / `availabilityCacheTatkal`), so reading the other
    costs no extra call. LD and SS each require a separate `quota=`-parameterised
    confirmtkt call that fills `availabilityCacheForQuota`. Values are confirmtkt's
    own quota codes."""

    GENERAL = "GN"
    TATKAL = "TQ"
    LADIES = "LD"
    SENIOR = "SS"
```

- [ ] **Step 3b: Route LD/SS in `cache_key`**

In `backend/app/providers/irctc/client.py`, replace `cache_key` (lines ~303-305):

```python
# confirmtkt cache key per quota: GN/TQ are bundled on the train object; LD/SS land
# in a single availabilityCacheForQuota filled by a quota=-parameterised search.
_QUOTA_CACHE_KEY = {
    BookingQuota.GENERAL: "availabilityCache",
    BookingQuota.TATKAL: "availabilityCacheTatkal",
    BookingQuota.LADIES: "availabilityCacheForQuota",
    BookingQuota.SENIOR: "availabilityCacheForQuota",
}


def cache_key(quota: BookingQuota) -> str:
    """The confirmtkt train-dict key holding this quota's per-class cache."""
    return _QUOTA_CACHE_KEY[quota]
```

- [ ] **Step 3c: Fix the Protocol docstring**

In `backend/app/providers/base.py`, replace the quota paragraph (lines ~22-25):

```python
    The optional `quota` selects which confirmtkt cache a method reads. GN and TQ
    are bundled in one response (reading the other costs no extra call); LD and SS
    each need a separate quota=-parameterised fetch. It defaults to GENERAL, so
    every existing call site behaves identically.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_irctc_provider.py::test_class_cache_routes_ladies_and_senior_to_for_quota_cache -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite (nothing regressed)**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/providers/irctc/client.py backend/app/providers/base.py backend/tests/test_irctc_provider.py
git commit -m "feat(quota): add Ladies/Senior to BookingQuota + cache routing"
```

---

### Task 2: `search_segment` quota param + cache-key widening

**Files:**
- Modify: `backend/app/providers/irctc/client.py` (`search_segment`, `_do_search`, cache annotations)
- Test: `backend/tests/test_irctc_provider.py`

**Interfaces:**
- Consumes: `BookingQuota` (Task 1).
- Produces: `search_segment(source, destination, date_ddmmyyyy, quota: BookingQuota | None = None)`; LD/SS add `quota=` to the upstream params and get their own cache entry; GN/TQ/None share the bundled entry.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_irctc_provider.py`:

```python
async def test_search_segment_isolates_ladies_senior_and_bundles_general_tatkal():
    seen_quota_params: list[str | None] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "cttrainsapi.confirmtkt.com":
            seen_quota_params.append(request.url.params.get("quota"))
            return httpx.Response(200, json={"data": {"trainList": []}})
        return httpx.Response(404, text="unexpected")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    client = IRCTCClient(client=http, retries=1, backoff=0.0)
    try:
        await client.search_segment("MMCT", "NDLS", "01-07-2026")                        # bundle (GN/TQ): 1 call
        await client.search_segment("MMCT", "NDLS", "01-07-2026")                        # cached: no call
        await client.search_segment("MMCT", "NDLS", "01-07-2026", BookingQuota.GENERAL)  # bundle: cached, no call
        await client.search_segment("MMCT", "NDLS", "01-07-2026", BookingQuota.TATKAL)   # bundle: cached, no call
        await client.search_segment("MMCT", "NDLS", "01-07-2026", BookingQuota.LADIES)   # quota=LD: new call
        await client.search_segment("MMCT", "NDLS", "01-07-2026", BookingQuota.SENIOR)   # quota=SS: new call
    finally:
        await http.aclose()
    # GN/TQ/None all collapse to ONE no-quota fetch; LD and SS each fetch once with their code.
    assert seen_quota_params == [None, "LD", "SS"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_irctc_provider.py::test_search_segment_isolates_ladies_senior_and_bundles_general_tatkal -v`
Expected: FAIL — `search_segment()` takes 4 positional args (no `quota`) → `TypeError`.

- [ ] **Step 3a: Widen the cache annotations**

In `backend/app/providers/irctc/client.py`, change the two annotations at lines ~91-93:

```python
        self._segment_cache: OrderedDict[tuple[str, str, str, str | None], tuple[float, list[dict]]] = OrderedDict()
        self._segment_inflight: dict[tuple[str, str, str, str | None], asyncio.Future] = {}
```

(The `_route_cache`/`_route_inflight` annotations on the surrounding lines are unchanged.)

- [ ] **Step 3b: Thread `quota` through `search_segment`**

Replace `search_segment` (lines ~256-276):

```python
    async def search_segment(
        self, source: str, destination: str, date_ddmmyyyy: str,
        quota: BookingQuota | None = None,
    ) -> list[dict]:
        """confirmtkt trainList for one segment+date+quota. GN/TQ share the bundled
        response (fetch_group None); LD/SS each fetch a quota=-parameterised response
        (fetch_group = the code). Cached with single-flight so concurrent callers for
        the same key share one HTTP request."""
        fetch_group = quota.value if quota in (BookingQuota.LADIES, BookingQuota.SENIOR) else None
        key = (source, destination, date_ddmmyyyy, fetch_group)
        now = time.monotonic()
        async with self._lock:
            hit = self._segment_cache.get(key)
            if hit and now - hit[0] < self._segment_ttl:
                self._segment_cache.move_to_end(key)
                return hit[1]

        async def _compute() -> list[dict]:
            result = await self._do_search(source, destination, date_ddmmyyyy, fetch_group)
            async with self._lock:
                self._segment_cache[key] = (time.monotonic(), result)
                self._segment_cache.move_to_end(key)
                while len(self._segment_cache) > self._segment_cache_max:
                    self._segment_cache.popitem(last=False)
            return result

        return await self._run_single_flight(key, self._segment_inflight, _compute)
```

- [ ] **Step 3c: Add the `quota` param to `_do_search`**

Replace `_do_search` (lines ~278-292):

```python
    async def _do_search(
        self, source: str, destination: str, date_ddmmyyyy: str, quota: str | None = None,
    ) -> list[dict]:
        params = {
            "sourceStationCode": source, "destinationStationCode": destination,
            "dateOfJourney": date_ddmmyyyy, "addAvailabilityCache": "true",
            "excludeMultiTicketAlternates": "false", "excludeBoostAlternates": "false",
            "sortBy": "DEFAULT", "enableNearby": "true", "enableTG": "true",
            "tGPlan": "CTG-3", "showTGPrediction": "false",
            "tgColor": "DEFAULT", "showPredictionGlobal": "true",
        }
        if quota is not None:
            params["quota"] = quota  # fills availabilityCacheForQuota for LD/SS
        payload = await self._get_json(CONFIRMTKT_SEARCH, params)
        data = payload.get("data") if isinstance(payload, dict) else None
        train_list = (data or {}).get("trainList") if isinstance(data, dict) else None
        return train_list or []
```

- [ ] **Step 3d: Update the single-flight test's stub signature**

In `backend/tests/test_irctc_provider.py`, the existing `test_owner_cancellation_does_not_poison_waiters` stubs `_do_search` with 3 params (line ~338). Widen it so `_compute` can pass `fetch_group`:

```python
    async def _blocking_search(source, destination, date, quota=None):
        started.set()
        await release.wait()
        return []
```

- [ ] **Step 4: Run the new + touched tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_irctc_provider.py -v`
Expected: PASS (including `test_owner_cancellation_does_not_poison_waiters` and the new isolation test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/irctc/client.py backend/tests/test_irctc_provider.py
git commit -m "feat(quota): thread quota through search_segment with per-quota cache key"
```

---

### Task 3: `search_quota_availability` provider method + Protocol + test doubles

**Files:**
- Modify: `backend/app/providers/base.py` (Protocol method + `RawClassOffer` import)
- Modify: `backend/app/providers/irctc/provider.py` (`build_quota_rows`, `search_quota_availability`)
- Modify: `backend/tests/conftest.py` (StubProvider stub)
- Modify: `backend/tests/fakes.py` (FakeRailDataProvider impl)
- Test: `backend/tests/test_train_search_extraction.py`

**Interfaces:**
- Consumes: `search_segment(..., quota)` (Task 2).
- Produces: `build_quota_rows(train_list) -> list[tuple[str, str, str, list[RawClassOffer]]]` (train_number, from_code, departure_time, offers); `RailDataProvider.search_quota_availability(source, destination, journey_date, quota) -> list[tuple[str, str, str, list[RawClassOffer]]]`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_train_search_extraction.py`:

```python
from app.providers.irctc.provider import build_quota_rows  # add to existing imports

_QUOTA_TRAIN = {
    "trainNumber": "12904",
    "fromStnCode": "NDLS",
    "departureTime": "04:00",
    "avlClassesSorted": ["3A", "SL"],
    "availabilityCacheForQuota": {
        "SL": {"availability": "RLWL3/WL3", "availabilityDisplayName": "WL 3", "fare": "755"},
        "3A": {"availability": "AVAILABLE-0042", "availabilityDisplayName": "AVL 42", "fare": "1980"},
        "ZZ": {"availability": "AVAILABLE-0001", "fare": "10"},  # class our enum doesn't model
    },
}


def test_build_quota_rows_reads_for_quota_cache_with_disambiguators():
    [(train_number, from_code, departure_time, offers)] = build_quota_rows([_QUOTA_TRAIN])
    assert (train_number, from_code, departure_time) == ("12904", "NDLS", "04:00")
    assert [o.travel_class.value for o in offers] == ["3A", "SL"]  # avlClassesSorted order; ZZ dropped
    sl = next(o for o in offers if o.travel_class.value == "SL")
    assert sl.raw_availability == "RLWL3/WL3"  # richer string, not the lossy "WL 3"
    assert sl.fare == 755


def test_build_quota_rows_empty_cache_yields_no_offers():
    train = {k: v for k, v in _QUOTA_TRAIN.items() if k != "availabilityCacheForQuota"}
    [(_n, _f, _d, offers)] = build_quota_rows([train])
    assert offers == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_train_search_extraction.py::test_build_quota_rows_reads_for_quota_cache_with_disambiguators -v`
Expected: FAIL — `ImportError: cannot import name 'build_quota_rows'`.

- [ ] **Step 3a: Add `build_quota_rows` to the provider**

In `backend/app/providers/irctc/provider.py`, add after `build_raw_trains_between` (after line ~89). It reuses the existing module-level `_offers` helper:

```python
def build_quota_rows(
    train_list: list[dict],
) -> list[tuple[str, str, str, list["RawClassOffer"]]]:
    """Shape a confirmtkt trainList (fetched with quota=LD|SS) into per-train rows of
    (train_number, from_code, departure_time, offers) read from availabilityCacheForQuota.
    The disambiguators let the frontend map rows back to cards — train_number is not
    unique under enableNearby."""
    out: list[tuple[str, str, str, list[RawClassOffer]]] = []
    for t in train_list:
        order = t.get("avlClassesSorted") or []
        out.append((
            str(t.get("trainNumber") or ""),
            t.get("fromStnCode") or "",
            t.get("departureTime") or "",
            _offers(t.get("availabilityCacheForQuota"), order),
        ))
    return out
```

- [ ] **Step 3b: Add `search_quota_availability` to the IRCTC provider**

In `backend/app/providers/irctc/provider.py`, add a method to `IRCTCRailDataProvider` (after `search_trains_between`, ~line 188):

```python
    async def search_quota_availability(
        self,
        source: str,
        destination: str,
        journey_date: dt.date,
        quota: BookingQuota,
    ) -> list[tuple[str, str, str, list[RawClassOffer]]]:
        # One confirmtkt call with quota=LD|SS fills availabilityCacheForQuota for
        # every train on the leg (shares the seat-finder's per-quota segment cache).
        train_list = await self._client.search_segment(
            source.upper(), destination.upper(), format_date(journey_date), quota
        )
        return build_quota_rows(train_list)
```

- [ ] **Step 3c: Add the Protocol method**

In `backend/app/providers/base.py`, add `RawClassOffer` to the schema import and declare the method on `RailDataProvider` (after `search_trains_between`):

```python
    async def search_quota_availability(
        self,
        source: str,
        destination: str,
        journey_date: dt.date,
        quota: BookingQuota,
    ) -> list[tuple[str, str, str, list[RawClassOffer]]]: ...
    # Per-train (train_number, from_code, departure_time, RAW per-class offers) for one
    # quota (LD/SS), read from confirmtkt's availabilityCacheForQuota. The service
    # normalizes the raw strings into TrainsQuotaAvailabilityResponse.
```

- [ ] **Step 3d: Add stubs to both test doubles**

In `backend/tests/conftest.py`, add to `StubProvider` (the seat-finder tests don't exercise it):

```python
    async def search_quota_availability(self, source, destination, journey_date, quota):
        # Train search has dedicated fakes; the seat-finder tests don't use this.
        return []
```

In `backend/tests/fakes.py`, add to `FakeRailDataProvider` (mirrors `search_trains_between` for one quota):

```python
    async def search_quota_availability(
        self,
        source: str,
        destination: str,
        journey_date: dt.date,
        quota: BookingQuota = BookingQuota.LADIES,
    ) -> list[tuple[str, str, str, list[RawClassOffer]]]:
        route = DEMO_TRAIN
        by_code = {s.code: s for s in route.stations}
        if source not in by_code or destination not in by_code:
            return []
        base = await self.get_fare(route.train_number, source, destination, journey_date, TravelClass.SL, quota)
        offers = [
            RawClassOffer(
                travel_class=TravelClass(code),
                raw_availability=await self.get_seat_status(
                    route.train_number, source, destination, journey_date, TravelClass(code), quota
                ),
                fare=int((base or 0) * mult),
            )
            for code, mult in self._CLASS_FARE_MULT.items()
        ]
        return [(route.train_number, source, "06:00", offers)]
```

- [ ] **Step 4: Run the extraction tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_train_search_extraction.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/base.py backend/app/providers/irctc/provider.py backend/tests/conftest.py backend/tests/fakes.py backend/tests/test_train_search_extraction.py
git commit -m "feat(quota): add search_quota_availability provider method"
```

---

### Task 4: Per-quota response schemas + service method + route

**Files:**
- Modify: `backend/app/schemas.py` (`TrainQuotaClasses`, `TrainsQuotaAvailabilityResponse`)
- Modify: `backend/app/services/train_search.py` (`search_quota`)
- Modify: `backend/app/routers/routes.py` (new route + comment fix)
- Test: `backend/tests/test_train_search_service.py`, `backend/tests/test_train_search_api.py`

**Interfaces:**
- Consumes: `search_quota_availability` (Task 3).
- Produces: `TrainSearchService.search_quota(source, destination, journey_date, quota) -> TrainsQuotaAvailabilityResponse`; `GET /api/trains-between/quota`.

- [ ] **Step 1: Write the failing service test**

Add to `backend/tests/test_train_search_service.py` (add `BookingQuota` to the schemas import on line 9):

```python
class _QuotaProvider:
    def __init__(self, rows):
        self._rows = rows
        self.calls: list[tuple] = []

    async def search_quota_availability(self, source, destination, journey_date, quota):
        self.calls.append((source, destination, journey_date, quota))
        return self._rows


async def test_search_quota_normalizes_rows_with_disambiguators():
    rows = [("12904", "NDLS", "04:00", [
        RawClassOffer(travel_class=TravelClass.AC3, raw_availability="AVAILABLE-0042", fare=1980),
        RawClassOffer(travel_class=TravelClass.SL, raw_availability="NOT AVAILABLE", fare=0),
    ])]
    provider = _QuotaProvider(rows)
    res = await TrainSearchService(provider).search_quota("ndls", "bct", _tomorrow(), BookingQuota.LADIES)
    assert (res.source, res.destination, res.quota) == ("NDLS", "BCT", BookingQuota.LADIES)
    [train] = res.trains
    assert (train.train_number, train.from_code, train.departure_time) == ("12904", "NDLS", "04:00")
    assert [c.travel_class.value for c in train.classes] == ["3A", "SL"]
    assert train.classes[0].availability.status is AvailabilityStatus.AVAILABLE
    sl = train.classes[1]
    assert sl.availability.status is AvailabilityStatus.NOT_BOOKABLE
    assert sl.fare is None  # 0 -> None business rule
    assert provider.calls == [("NDLS", "BCT", _tomorrow(), BookingQuota.LADIES)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_train_search_service.py::test_search_quota_normalizes_rows_with_disambiguators -v`
Expected: FAIL — `AttributeError: 'TrainSearchService' object has no attribute 'search_quota'`.

- [ ] **Step 3a: Add the response schemas**

In `backend/app/schemas.py`, add after `TrainsBetweenResponse` (after line ~144):

```python
class TrainQuotaClasses(BaseModel):
    """One train's per-class availability under a single quota. Carries the card's
    disambiguators — train_number is NOT unique within a result (enableNearby)."""
    train_number: str
    from_code: str
    departure_time: str
    classes: list[ClassAvailability]


class TrainsQuotaAvailabilityResponse(BaseModel):
    source: str
    destination: str
    journey_date: dt.date
    quota: BookingQuota
    trains: list[TrainQuotaClasses]
```

- [ ] **Step 3b: Add `search_quota` to the service**

In `backend/app/services/train_search.py`, extend the schemas import to include `BookingQuota, TrainQuotaClasses, TrainsQuotaAvailabilityResponse`, then add a method to `TrainSearchService` (after `search`, ~line 41):

```python
    async def search_quota(
        self, source: str, destination: str, journey_date: dt.date, quota: BookingQuota
    ) -> TrainsQuotaAvailabilityResponse:
        source = source.strip().upper()
        destination = destination.strip().upper()
        validate_journey_date(journey_date)
        rows = await self._provider.search_quota_availability(
            source, destination, journey_date, quota
        )
        return TrainsQuotaAvailabilityResponse(
            source=source,
            destination=destination,
            journey_date=journey_date,
            quota=quota,
            trains=[
                TrainQuotaClasses(
                    train_number=train_number,
                    from_code=from_code,
                    departure_time=departure_time,
                    classes=[self._to_class(o) for o in offers],
                )
                for train_number, from_code, departure_time, offers in rows
            ],
        )
```

- [ ] **Step 4a: Run the service test (passes)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_train_search_service.py -v`
Expected: PASS.

- [ ] **Step 4b: Write the failing route test**

Add to `backend/tests/test_train_search_api.py`:

```python
class _QuotaProvider:
    def __init__(self, rows=None, raises=None):
        self._rows = rows or []
        self._raises = raises

    async def search_quota_availability(self, source, destination, journey_date, quota):
        if self._raises is not None:
            raise self._raises
        return self._rows


def test_trains_between_quota_happy_path():
    rows = [("12952", "NDLS", "16:25", [
        RawClassOffer(travel_class=TravelClass.SL, raw_availability="AVAILABLE-0010", fare=755),
    ])]
    _override(_QuotaProvider(rows))
    res = client.get("/api/trains-between/quota", **_params(quota="LD"))
    assert res.status_code == 200
    body = res.json()
    assert body["quota"] == "LD"
    [train] = body["trains"]
    assert (train["train_number"], train["from_code"], train["departure_time"]) == ("12952", "NDLS", "16:25")
    assert train["classes"][0]["availability"]["status"] == "AVAILABLE"


def test_trains_between_quota_unknown_quota_422():
    _override(_QuotaProvider())
    res = client.get("/api/trains-between/quota", **_params(quota="ZZ"))
    assert res.status_code == 422
```

- [ ] **Step 5: Run route test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_train_search_api.py::test_trains_between_quota_happy_path -v`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 6: Add the route**

In `backend/app/routers/routes.py`: add `TrainsQuotaAvailabilityResponse` to the schemas import; change the `find_optimal_route` quota comment (line ~30) from `# GN | TQ; 422s on an unknown code` to `# GN | TQ | LD | SS; 422s on an unknown code`; and add the route after `trains_between` (after line ~58):

```python
@router.get("/trains-between/quota", response_model=TrainsQuotaAvailabilityResponse)
async def trains_between_quota(
    provider: ProviderDep,
    source: Annotated[str, Query(min_length=1, max_length=5, description="Source station code")],
    destination: Annotated[str, Query(min_length=1, max_length=5, description="Destination station code")],
    date: dt.date,
    quota: BookingQuota,  # LD | SS (GN/TQ arrive in /trains-between); 422s on unknown
) -> TrainsQuotaAvailabilityResponse:
    """One quota's per-class availability for every train on the leg — the lazy
    fetch for Ladies/Senior, which aren't in the bundled /trains-between response."""
    return await TrainSearchService(provider).search_quota(source, destination, date, quota)
```

- [ ] **Step 7: Run the route tests (pass)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_train_search_api.py -v`
Expected: PASS (happy path + 422).

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/services/train_search.py backend/app/routers/routes.py backend/tests/test_train_search_service.py backend/tests/test_train_search_api.py
git commit -m "feat(quota): add /api/trains-between/quota lazy per-quota endpoint"
```

---

### Task 5: Surface `allowed_quotas` per train

**Files:**
- Modify: `backend/app/schemas.py` (`RawTrainBetween`, `TrainBetween`)
- Modify: `backend/app/providers/irctc/provider.py` (`build_raw_trains_between`)
- Modify: `backend/app/services/train_search.py` (`_to_train_between`)
- Test: `backend/tests/test_train_search_extraction.py`, `backend/tests/test_train_search_service.py`

**Interfaces:**
- Produces: `TrainBetween.allowed_quotas: list[str]` (confirmtkt's per-train `allowedQuotas`).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_train_search_extraction.py`:

```python
def test_allowed_quotas_surfaced_from_payload():
    train = {**_TRAIN, "allowedQuotas": ["GN", "TQ", "LD", "SS"]}
    [t] = build_raw_trains_between([train])
    assert t.allowed_quotas == ["GN", "TQ", "LD", "SS"]


def test_allowed_quotas_defaults_empty_when_absent():
    [t] = build_raw_trains_between([_TRAIN])  # _TRAIN has no allowedQuotas key
    assert t.allowed_quotas == []
```

Add to `backend/tests/test_train_search_service.py`:

```python
async def test_allowed_quotas_passed_through_to_response():
    raw = _raw(
        general=[RawClassOffer(travel_class=TravelClass.SL, raw_availability="AVAILABLE-0010", fare=755)],
        tatkal=[],
    ).model_copy(update={"allowed_quotas": ["GN", "LD"]})
    res = await TrainSearchService(_FakeProvider([raw])).search("NDLS", "BCT", _tomorrow())
    assert res.trains[0].allowed_quotas == ["GN", "LD"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_train_search_extraction.py::test_allowed_quotas_surfaced_from_payload tests/test_train_search_service.py::test_allowed_quotas_passed_through_to_response -v`
Expected: FAIL — `RawTrainBetween` has no `allowed_quotas` field.

- [ ] **Step 3a: Add the fields**

In `backend/app/schemas.py`, add to `RawTrainBetween` (after line ~113, end of class):

```python
    allowed_quotas: list[str] = []
```

And to `TrainBetween` (after line ~137):

```python
    allowed_quotas: list[str] = []
```

- [ ] **Step 3b: Populate from the payload**

In `backend/app/providers/irctc/provider.py`, in `build_raw_trains_between`'s `RawTrainBetween(...)` construction (after `tatkal_offers=...`, ~line 86), add:

```python
                allowed_quotas=t.get("allowedQuotas") or [],
```

- [ ] **Step 3c: Copy through the service**

In `backend/app/services/train_search.py`, in `_to_train_between`'s `TrainBetween(...)` construction (after `tatkal=...`, ~line 58), add:

```python
            allowed_quotas=raw.allowed_quotas,
```

- [ ] **Step 4: Run the tests (pass) + full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_train_search_extraction.py tests/test_train_search_service.py -v`
Then: `.venv/Scripts/python.exe -m pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/providers/irctc/provider.py backend/app/services/train_search.py backend/tests/test_train_search_extraction.py backend/tests/test_train_search_service.py
git commit -m "feat(quota): surface per-train allowed_quotas"
```

---

### Task 6: Seat-finder quota threading + recommendation notes

**Files:**
- Modify: `backend/app/providers/irctc/provider.py` (`get_seat_status`, `get_fare`, `get_class_options`)
- Modify: `backend/app/services/recommendations.py` (note/action map + stale comments)
- Test: `backend/tests/test_irctc_provider.py`, `backend/tests/test_recommendation_service.py`

**Interfaces:**
- Consumes: `search_segment(..., quota)` (Task 2), `cache_key` (Task 1).
- Produces: seat-finder reads LD/SS via `availabilityCacheForQuota`; LD/SS recommendations carry quota-specific notes.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_irctc_provider.py`:

```python
CT_PAYLOAD_FORQUOTA = {
    "data": {
        "trainList": [
            {
                "trainNumber": "12951",
                "availabilityCache": {"SL": {"availabilityDisplayName": "AVAILABLE-0042", "fare": 1245}},
                "availabilityCacheForQuota": {"SL": {"availabilityDisplayName": "LADIES WL3", "fare": 1300}},
            }
        ]
    }
}


async def test_seat_status_and_fare_read_for_quota_cache_for_ladies():
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_FORQUOTA))
    try:
        status = await provider.get_seat_status(
            "12951", "MMCT", "NDLS", DATE, TravelClass.SL, BookingQuota.LADIES
        )
        fare = await provider.get_fare(
            "12951", "MMCT", "NDLS", DATE, TravelClass.SL, BookingQuota.LADIES
        )
    finally:
        await http.aclose()
    assert status == "LADIES WL3"  # the availabilityCacheForQuota cell, not the general "AVAILABLE-0042"
    assert fare == 1300
```

Add to `backend/tests/test_recommendation_service.py`:

```python
async def test_ladies_quota_recommendation_carries_ladies_note_and_action():
    provider = StubProvider({("A", "F"): "AVAILABLE 5"})
    res = await RecommendationService(provider).find_optimal_route(
        "12345", "A", "F", tomorrow(), TravelClass.SL, BookingQuota.LADIES
    )
    assert res.quota is BookingQuota.LADIES
    assert any("Ladies quota" in n for rec in res.recommendations for n in rec.notes)
    assert any("in Ladies quota" in rec.action for rec in res.recommendations)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_irctc_provider.py::test_seat_status_and_fare_read_for_quota_cache_for_ladies tests/test_recommendation_service.py::test_ladies_quota_recommendation_carries_ladies_note_and_action -v`
Expected: FAIL — seat status returns "NOT AVAILABLE" (search_segment didn't fetch the LD cache); no "Ladies quota" note.

- [ ] **Step 3a: Pass `quota` into `search_segment` at the three seat-finder call sites**

In `backend/app/providers/irctc/provider.py`, in `get_seat_status` (line ~122-125), `get_fare` (line ~143-146), and `get_class_options` (line ~160-163), add `quota` as the 4th argument to each `self._client.search_segment(...)` call:

```python
        train = find_train(
            await self._client.search_segment(source, destination, format_date(journey_date), quota),
            train_number,
        )
```

(All three call sites already have `quota` in scope from their method signature; `class_cache`/`cache_key` already route by quota.)

- [ ] **Step 3b: Generalise the recommendation notes**

In `backend/app/services/recommendations.py`, add module-level maps after the imports (near line ~31):

```python
# Per-quota note + action suffix for non-General bookings. General needs neither.
_QUOTA_NOTE = {
    BookingQuota.TATKAL: "Book under the Tatkal quota on IRCTC — it opens ~1 day "
                         "before travel and carries a higher fare than General.",
    BookingQuota.LADIES: "Book under the Ladies quota on IRCTC — reserved for women "
                         "travellers (and a child under 12 travelling with them).",
    BookingQuota.SENIOR: "Book under the Senior Citizen quota on IRCTC — for eligible "
                         "senior citizens; carry valid age proof.",
}
_QUOTA_ACTION_SUFFIX = {
    BookingQuota.TATKAL: " in Tatkal quota",
    BookingQuota.LADIES: " in Ladies quota",
    BookingQuota.SENIOR: " in Senior Citizen quota",
}
```

In `_build_recommendation`, replace the Tatkal note block (lines ~293-298):

```python
        notes: list[str] = []
        quota_note = _QUOTA_NOTE.get(quota)
        if quota_note:
            notes.append(quota_note)
```

…and the action-suffix block (lines ~318-319):

```python
        action += _QUOTA_ACTION_SUFFIX.get(quota, "")
```

(Delete the old `if quota is BookingQuota.TATKAL: action += " in Tatkal quota"` and the old Tatkal-note `if`.)

- [ ] **Step 3c: Fix the now-stale "no extra requests" comments**

In `_build_alternatives` docstring (line ~198-199), replace "Reuses the cached pair responses, so it costs no extra requests." with:

```python
        just the direct leg. Reuses the searched cell's cached GN/TQ pair responses
        (an LD/SS search adds one bundled GN/TQ fetch here — still single-flighted).
```

In `_evaluate_class` docstring (line ~146-148), replace "so it issues no extra upstream requests beyond the searched cell's." with:

```python
        alternative (class × quota) cell — issuing no extra upstream requests beyond
        the searched cell's for a GN/TQ search (an LD/SS search adds one GN/TQ bundle).
```

- [ ] **Step 4: Run the tests (pass) + full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_irctc_provider.py tests/test_recommendation_service.py -v`
Then: `.venv/Scripts/python.exe -m pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/irctc/provider.py backend/app/services/recommendations.py backend/tests/test_irctc_provider.py backend/tests/test_recommendation_service.py
git commit -m "feat(quota): read LD/SS in seat-finder + quota-specific recommendation notes"
```

---

### Task 7: Frontend — quota types/client + Train-Search BookingQuota rename

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/TrainSearchForm.tsx`
- Modify: `frontend/src/components/TrainSearchPanel.tsx`
- Modify: `frontend/src/components/TrainSearchResults.tsx`
- Modify: `frontend/src/components/TrainBetweenCard.tsx`

**Interfaces:**
- Produces: `QUOTAS` includes LD/SS; `BookingQuota` is the train-search quota type; `TrainQuotaClasses`, `TrainsQuotaAvailabilityResponse`, `searchTrainsQuotaAvailability`; `TrainBetween.allowed_quotas`. (Train-search UI still offers GN/TQ only — LD/SS exposed in Task 10.)

- [ ] **Step 1: Update `client.ts`**

In `frontend/src/api/client.ts`:

(a) Extend `QUOTAS` (lines ~21-24):

```ts
export const QUOTAS = [
  { value: 'GN', label: 'General' },
  { value: 'TQ', label: 'Tatkal' },
  { value: 'LD', label: 'Ladies' },
  { value: 'SS', label: 'Senior Citizen' },
] as const
```

(b) Add `allowed_quotas` to `TrainBetween` (after `tatkal: ClassAvailability[]`, line ~186):

```ts
  allowed_quotas: string[]
```

(c) Replace the `TrainQuota` block (lines ~196-198) — delete the type, add the per-quota response types:

```ts
export interface TrainQuotaClasses {
  train_number: string
  from_code: string
  departure_time: string
  classes: ClassAvailability[]
}

export interface TrainsQuotaAvailabilityResponse {
  source: string
  destination: string
  journey_date: string
  quota: BookingQuota
  trains: TrainQuotaClasses[]
}
```

(d) Add the lazy-fetch call at the end of the file:

```ts
export function searchTrainsQuotaAvailability(
  source: string,
  destination: string,
  date: string, // YYYY-MM-DD
  quota: BookingQuota,
  signal?: AbortSignal,
): Promise<TrainsQuotaAvailabilityResponse> {
  const params = new URLSearchParams({ source, destination, date, quota })
  return request<TrainsQuotaAvailabilityResponse>(`/api/trains-between/quota?${params}`, signal)
}
```

- [ ] **Step 2: Rename `TrainQuota` → `BookingQuota` in the train-search components**

(a) `frontend/src/components/TrainSearchPanel.tsx`: change the import `type TrainQuota` → `type BookingQuota`, and `useState<TrainQuota>('general')` (line ~33) → `useState<BookingQuota>('GN')`.

(b) `frontend/src/components/TrainSearchResults.tsx`: change the prop type `quota: TrainQuota` → `quota: BookingQuota` (import swap), and the header (line ~33) from rendering the raw code to a label:

```tsx
import { QUOTAS, type TrainBetween, type TrainsBetweenResponse } from '../api/client'
import type { BookingQuota } from '../api/client'
```

```tsx
          {trains.length} {trains.length === 1 ? 'train' : 'trains'} ·{' '}
          {QUOTAS.find((q) => q.value === quota)?.label ?? quota}
```

(Replace `quota: TrainQuota` in `TrainSearchResultsProps` with `quota: BookingQuota`.)

(c) `frontend/src/components/TrainBetweenCard.tsx`: change `quota: TrainQuota` → `quota: BookingQuota` (import swap), and the class selection (line ~56) + empty-state ternary (line ~124) from `'tatkal'` → `'TQ'`:

```tsx
  const classes = quota === 'TQ' ? train.tatkal : train.general
```

```tsx
            {quota === 'TQ'
              ? 'Tatkal availability opens ~1 day before travel.'
              : 'No availability data for this train.'}
```

- [ ] **Step 3: Keep the Train-Search quota control at GN/TQ for now**

In `frontend/src/components/TrainSearchForm.tsx`: delete the local `const QUOTAS` shadow (lines ~14-17) and the `TrainQuota` import; import the shared `QUOTAS` + `BookingQuota`; retype the props; and render a GN/TQ subset (LD/SS join in Task 10):

```tsx
import { QUOTAS, type BookingQuota, type Station } from '../api/client'
```

```tsx
interface TrainSearchFormProps {
  onSearch: (q: { source: string; destination: string; date: string }) => void
  searching: boolean
  quota: BookingQuota
  onQuotaChange: (quota: BookingQuota) => void
}

// Train Search offers General/Tatkal until the lazy LD/SS fetch lands (Task 10).
const SHOWN_QUOTAS = QUOTAS.filter((q) => q.value === 'GN' || q.value === 'TQ')
```

Then in the quota pill group, map over `SHOWN_QUOTAS` instead of the deleted local `QUOTAS`.

- [ ] **Step 4: Typecheck + build**

Run (from `frontend/`): `npx tsc --noEmit && npm run build`
Expected: no type errors, build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/components/TrainSearchForm.tsx frontend/src/components/TrainSearchPanel.tsx frontend/src/components/TrainSearchResults.tsx frontend/src/components/TrainBetweenCard.tsx
git commit -m "feat(quota): client types + Train-Search BookingQuota rename"
```

---

### Task 8: Frontend — quota pickers become dropdowns

**Files:**
- Modify: `frontend/src/components/SearchForm.tsx` (Seat Finder — now offers all 4)
- Modify: `frontend/src/components/TrainSearchForm.tsx` (Train Search — GN/TQ dropdown)

**Interfaces:**
- Consumes: `QUOTAS` (Task 7). Seat-finder LD/SS now reach `/api/find-optimal-route` (backend ready).

- [ ] **Step 1: Seat-Finder quota → `<select>`**

In `frontend/src/components/SearchForm.tsx`, replace the quota button-group block (the `<div role="group" aria-label="Booking quota">…</div>`, lines ~236-259) with a `<select>` matching the Class field:

```tsx
        <div>
          <label htmlFor="quota" className={LABEL}>
            Quota
          </label>
          <select
            id="quota"
            name="quota"
            className={FIELD}
            value={quota}
            onChange={(e) => onQuotaChange(e.target.value as BookingQuota)}
          >
            {QUOTAS.map((q) => (
              <option key={q.value} value={q.value}>
                {q.label}
              </option>
            ))}
          </select>
        </div>
```

Ensure `QUOTAS` and `BookingQuota` are imported in `SearchForm.tsx` (it already imports `QUOTAS`, `type BookingQuota`).

- [ ] **Step 2: Train-Search quota → `<select>`**

In `frontend/src/components/TrainSearchForm.tsx`, replace the quota pill group (`<div role="group" aria-label="Quota">…</div>`) with the same `<select>`, driven by `SHOWN_QUOTAS`:

```tsx
        <div>
          <label htmlFor="ts-quota" className={LABEL}>
            Quota
          </label>
          <select
            id="ts-quota"
            name="quota"
            className={FIELD}
            value={quota}
            onChange={(e) => onQuotaChange(e.target.value as BookingQuota)}
          >
            {SHOWN_QUOTAS.map((q) => (
              <option key={q.value} value={q.value}>
                {q.label}
              </option>
            ))}
          </select>
        </div>
```

- [ ] **Step 3: Typecheck + build**

Run (from `frontend/`): `npx tsc --noEmit && npm run build`
Expected: clean.

- [ ] **Step 4: Manual check (optional but recommended)**

Start the app; in the Seat Finder the Quota dropdown now lists General/Tatkal/Ladies/Senior Citizen, and selecting Ladies returns LD recommendations. (Train Search still shows General/Tatkal only.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SearchForm.tsx frontend/src/components/TrainSearchForm.tsx
git commit -m "feat(quota): quota pickers become dropdowns; seat-finder offers LD/SS"
```

---

### Task 9: Frontend — Train-Search lazy fetch, merge & card refactor

**Files:**
- Modify: `frontend/src/components/TrainSearchPanel.tsx`
- Modify: `frontend/src/components/TrainSearchResults.tsx`
- Modify: `frontend/src/components/TrainBetweenCard.tsx`

**Interfaces:**
- Consumes: `searchTrainsQuotaAvailability`, `TrainsQuotaAvailabilityResponse`, `ClassAvailability`, `TrainBetween.allowed_quotas` (Task 7).
- Produces: `TrainBetweenCard` props `{ train, quota, classes, onFindSeat }`; the panel resolves classes per quota (GN/TQ from the bundle, LD/SS from a composite-keyed cache).

- [ ] **Step 1: Panel — lazy fetch + composite-key cache**

In `frontend/src/components/TrainSearchPanel.tsx`:

(a) Extend imports:

```tsx
import {
  ApiError,
  searchTrainsBetween,
  searchTrainsQuotaAvailability,
  type BookingQuota,
  type ClassAvailability,
  type TrainBetween,
  type TrainsBetweenResponse,
} from '../api/client'
```

(b) Add a composite key helper (module scope) — it MUST match the card's React key:

```tsx
// train_number is not unique within a result (enableNearby), so quota rows are
// keyed by the same composite the card list uses.
const rowKey = (t: { train_number: string; from_code: string; departure_time: string }) =>
  `${t.train_number}-${t.from_code}-${t.departure_time}`
```

(c) Add per-quota cache + loading state next to `quota`/`state` (replace the `useState<BookingQuota>('GN')` line and add new state):

```tsx
  const [quota, setQuota] = useState<BookingQuota>('GN')
  // Lazily-fetched LD/SS availability, keyed by quota then by composite row key.
  const [quotaCache, setQuotaCache] = useState<Partial<Record<BookingQuota, Map<string, ClassAvailability[]>>>>({})
  const [quotaLoading, setQuotaLoading] = useState(false)
  const quotaAbortRef = useRef<AbortController | null>(null)
```

(d) Clear the cache whenever a new base search runs — inside `handleSearch`, right after `setState({ status: 'loading' })`:

```tsx
      setQuotaCache({}) // a new route/date invalidates lazily-fetched quotas
```

(e) Add a quota-change handler that lazily fetches LD/SS:

```tsx
  function handleQuotaChange(next: BookingQuota) {
    setQuota(next)
    if (state.status !== 'success') return
    if (next === 'GN' || next === 'TQ') return // bundled in the base response
    if (quotaCache[next]) return // already fetched
    quotaAbortRef.current?.abort()
    const controller = new AbortController()
    quotaAbortRef.current = controller
    setQuotaLoading(true)
    searchTrainsQuotaAvailability(state.data.source, state.data.destination, state.data.journey_date, next, controller.signal)
      .then((res) => {
        const byRow = new Map<string, ClassAvailability[]>()
        for (const t of res.trains) byRow.set(rowKey(t), t.classes)
        setQuotaCache((prev) => ({ ...prev, [next]: byRow }))
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        // A failed quota fetch leaves cards in their empty state; surface nothing fatal.
      })
      .finally(() => {
        if (quotaAbortRef.current === controller) setQuotaLoading(false)
      })
  }
```

(f) Wire the form + results to the new handler/state. Change `onQuotaChange={setQuota}` → `onQuotaChange={handleQuotaChange}`, and pass the resolver to results:

```tsx
      {state.status === 'success' && (
        <TrainSearchResults
          data={state.data}
          quota={quota}
          quotaLoading={quotaLoading}
          onFindSeat={handleFindSeat}
          classesFor={(t) =>
            quota === 'GN'
              ? t.general
              : quota === 'TQ'
                ? t.tatkal
                : quotaCache[quota]?.get(rowKey(t)) ?? []
          }
        />
      )}
```

(`handleFindSeat` is the existing deep-link handler already in this panel — keep it unchanged.)
```

- [ ] **Step 2: Results — pass resolved classes + loading to each card**

In `frontend/src/components/TrainSearchResults.tsx`, extend the props and the card render:

```tsx
import { QUOTAS, type ClassAvailability, type TrainBetween, type TrainsBetweenResponse } from '../api/client'
import type { BookingQuota } from '../api/client'
import { TrainBetweenCard } from './TrainBetweenCard'

interface TrainSearchResultsProps {
  data: TrainsBetweenResponse
  quota: BookingQuota
  quotaLoading: boolean
  onFindSeat: (train: TrainBetween) => void
  classesFor: (train: TrainBetween) => ClassAvailability[]
}
```

Update the destructure + the grid. `onFindSeat` is threaded through unchanged (the existing deep-link handler). Render each card with resolved classes, and dim the grid while a quota loads:

```tsx
export function TrainSearchResults({ data, quota, quotaLoading, onFindSeat, classesFor }: TrainSearchResultsProps) {
  const { source, destination, journey_date, trains } = data
```

```tsx
        <div className={`mt-6 grid grid-cols-1 gap-5 md:grid-cols-2 ${quotaLoading ? 'opacity-50' : ''}`}>
          {trains.map((t) => (
            <TrainBetweenCard
              key={`${t.train_number}-${t.from_code}-${t.departure_time}`}
              train={t}
              quota={quota}
              classes={classesFor(t)}
              onFindSeat={onFindSeat}
            />
          ))}
        </div>
```

- [ ] **Step 3: Card — take resolved `classes`, quota-aware empty state**

In `frontend/src/components/TrainBetweenCard.tsx`:

(a) Props + remove the internal `const classes = quota === 'TQ' ? …` derivation:

```tsx
interface TrainBetweenCardProps {
  train: TrainBetween
  quota: BookingQuota
  classes: ClassAvailability[]
  onFindSeat: (train: TrainBetween) => void
}

export function TrainBetweenCard({ train, quota, classes, onFindSeat }: TrainBetweenCardProps) {
```

(b) Add a per-quota empty-state helper (module scope):

```tsx
function emptyHint(quota: BookingQuota, allowed: string[]): string {
  if (!allowed.includes(quota)) {
    const label = QUOTAS.find((q) => q.value === quota)?.label ?? quota
    return `${label} quota is not offered on this train.`
  }
  if (quota === 'TQ') return 'Tatkal availability opens ~1 day before travel.'
  return 'No availability data for this train.'
}
```

(c) Replace the empty-state branch (the current `quota === 'tatkal' ? … : …` paragraph) with:

```tsx
        ) : (
          <p className="rounded-md border border-dashed border-rail-200 px-3 py-2 text-xs italic text-rail-700">
            {emptyHint(quota, train.allowed_quotas)}
          </p>
        )}
```

(d) Ensure imports include `QUOTAS`, `type BookingQuota`, `type ClassAvailability`, `type TrainBetween`.

- [ ] **Step 4: Typecheck + build**

Run (from `frontend/`): `npx tsc --noEmit && npm run build`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TrainSearchPanel.tsx frontend/src/components/TrainSearchResults.tsx frontend/src/components/TrainBetweenCard.tsx
git commit -m "feat(quota): Train-Search lazy LD/SS fetch + composite-key merge + card refactor"
```

---

### Task 10: Frontend — expose Ladies/Senior in Train Search

**Files:**
- Modify: `frontend/src/components/TrainSearchForm.tsx`

**Interfaces:**
- Consumes: the lazy fetch machinery (Task 9). This is the final flip that lets users pick LD/SS in Train Search.

- [ ] **Step 1: Show all four quotas**

In `frontend/src/components/TrainSearchForm.tsx`, delete the `SHOWN_QUOTAS` constant and render the full shared `QUOTAS` in the `<select>`:

```tsx
            {QUOTAS.map((q) => (
              <option key={q.value} value={q.value}>
                {q.label}
              </option>
            ))}
```

- [ ] **Step 2: Typecheck + build**

Run (from `frontend/`): `npx tsc --noEmit && npm run build`
Expected: clean.

- [ ] **Step 3: Manual verification (the whole feature)**

Start the app (`docker compose up -d --build frontend` if using the baked image, per project memory). In **Train Search**: search a near-date route (e.g. NDLS→MMCT, tomorrow). Toggle Quota to **Ladies** → brief loading, cards show LD availability; toggle **Senior Citizen** → SS availability; toggle back to General → instant. A train that doesn't offer the quota shows "… quota is not offered on this train." In **Seat Finder**: pick **Ladies**, search a near-date train → recommendations note "Book under the Ladies quota."

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/TrainSearchForm.tsx
git commit -m "feat(quota): expose Ladies/Senior in Train Search quota picker"
```

---

## Self-Review

**Spec coverage:** enum + cache routing (Task 1), search_segment quota + key (Task 2), provider method + doubles (Task 3), response schemas + service + route (Task 4), allowed_quotas (Task 5), seat-finder threading + notes + stale comments (Task 6), client types/call + rename + header label (Task 7), dropdowns (Task 8), lazy fetch + composite-key merge + card contract + empty states (Task 9), expose LD/SS (Task 10). Docstring corrections: BookingQuota + base.py (Task 1); routes.py comment (Task 4). PT explicitly excluded (Global Constraints). All spec sections map to a task.

**Composite-key consistency:** `rowKey` in `TrainSearchPanel` (Task 9) and the card's React `key` in `TrainSearchResults` (Tasks 7/9) are both `` `${train_number}-${from_code}-${departure_time}` ``; the backend `TrainQuotaClasses` (Task 4) carries those three fields, populated by `build_quota_rows` (Task 3). Consistent end-to-end.

**Type consistency:** `search_quota_availability` returns `list[tuple[str, str, str, list[RawClassOffer]]]` in the Protocol (Task 3), the IRCTC impl (Task 3), and both doubles (Task 3); consumed by `search_quota` (Task 4) which unpacks `(train_number, from_code, departure_time, offers)`. `BookingQuota` is the single quota type across both surfaces after Task 7.
