# Ladies & Senior-Citizen Quotas — Design Spec

**Date:** 2026-06-18
**Status:** Approved (brainstorming), pending implementation plan
**Related:** [2026-06-17-train-search-design.md](2026-06-17-train-search-design.md), [2026-06-17-seat-finder-quota-design.md](2026-06-17-seat-finder-quota-design.md)

> Revised 2026-06-18 after a multi-agent adversarial review against the codebase
> (16 confirmed findings folded in): composite cache key, explicit card contract,
> the `TrainQuota→BookingQuota` value-rename, and a corrected Testing section.

## Goal

Let users check **Ladies (LD)** and **Senior Citizen (SS)** quota availability — in
addition to today's **General (GN)** and **Tatkal (TQ)** — on **both** product
surfaces (the Seat Finder and Train Search), with the quota picker restyled as a
dropdown like the Class field.

## Why this shape (investigation findings)

All findings below were verified against the **live confirmtkt API** during
brainstorming (2026-06-18):

1. **confirmtkt natively supports GN/TQ/LD/SS — one upstream, same parser.** A
   train object in the existing `/api/v1/trains/search` response carries
   `allowedQuotas` (observed value `['GN','TQ','SS','LD']` across NDLS→MMCT,
   NDLS→LKO, HWH→NDLS, SBC→MAS) and an (initially empty) `availabilityCacheForQuota`
   field. Passing `quota=LD` or `quota=SS` to the **same** search endpoint
   populates `availabilityCacheForQuota` with the **identical per-class field shape**
   as `availabilityCache` (`availability`, `availabilityDisplayName`, `fare`, …).
   So `app.core.parser.parse_availability` and `app.core.ranking.confirmation_probability`
   work unchanged.

2. **One call per quota returns all trains × classes.** A `quota=LD` search returns
   the LD cache for every train on the leg in a single request — *not* a
   per-train/class fan-out. This is as cheap as the existing General bundle.

3. **GN + TQ remain free in the first call.** The existing no-`quota` search bundles
   `availabilityCache` (GN) and `availabilityCacheTatkal` (TQ). LD/SS each need their
   own `quota=`-parameterised call.

4. **Premium Tatkal (PT) is NOT obtainable and is dropped.** PT never appears in
   `allowedQuotas` on any route, and both confirmtkt endpoints return empty for it:
   the bundled search (`availabilityCacheForQuota` empty for `quota=PT`) and the
   dedicated per-train availability endpoint confirmtkt's own site uses
   (`/api/v1/availability/2monthcalendar?...&quota=PT` → HTTP 200 with **0 dated
   entries**, while GN/TQ/LD/SS populate — verified on 12506, 12952 Mumbai Rajdhani,
   12302 Howrah Rajdhani, 12951). PT uses dynamic pricing with no waitlist and is
   resolved only inside IRCTC's live booking flow, so there is no availability cache
   to read. **Out of scope.**

5. **Booking-window behaviour.** TQ (and, were it available, PT) only populate
   within ~1 day of travel — the same window the UI already explains for Tatkal.
   LD/SS populate for the full advance window like General.

## Quota model

`BookingQuota` (an existing `str, Enum` in `app/schemas.py`) gains two members:

| Code | Member          | confirmtkt cache key            | Fetched              |
|------|-----------------|---------------------------------|----------------------|
| `GN` | `GENERAL`       | `availabilityCache`             | first search (free)  |
| `TQ` | `TATKAL`        | `availabilityCacheTatkal`       | first search (free)  |
| `LD` | `LADIES` (new)  | `availabilityCacheForQuota`     | lazy, on first select|
| `SS` | `SENIOR` (new)  | `availabilityCacheForQuota`     | lazy, on first select|

**Docstrings to correct** (both assert a now-false "no extra upstream call"
invariant): the `BookingQuota` docstring in `app/schemas.py` **and** the
`RailDataProvider` Protocol docstring in `app/providers/base.py:21-24`
("…both quotas come from the same cached response, so reading the other one costs no
extra upstream request"). Reword both: GN/TQ share the one bundled response; LD/SS
each require a separate `quota=`-parameterised call that fills
`availabilityCacheForQuota`. (`build_raw_trains_between`'s docstring in
`provider.py` describes the unchanged GN+TQ bundle and stays correct — leave it.)

## Backend

### `app/providers/irctc/client.py`

- **`search_segment(source, destination, date_ddmmyyyy, quota: BookingQuota | None = None)`** —
  new optional `quota`. The segment cache key becomes
  `(source, destination, date_ddmmyyyy, fetch_group)` where
  `fetch_group = None` for GN/TQ/`None` (the bundle) and `quota.value` for LD/SS.
  This keeps GN and TQ sharing the one bundled response while giving LD and SS each
  their own cached call. Single-flight and LRU bounds are otherwise unchanged.
  - **Type-annotation edits this implies:** widen `_segment_cache`
    (`OrderedDict[tuple[str, str, str], …]`) and `_segment_inflight`
    (`dict[tuple[str, str, str], asyncio.Future]`) at `client.py:92-93` to
    `tuple[str, str, str, str | None]`, and update the key construction in
    `search_segment` (`client.py:259`) to include `fetch_group`. (No type checker
    runs in CI, but keep annotations honest.)
- **`_do_search(...)`** — gains the same `quota` arg; adds `"quota": quota.value` to
  the confirmtkt params **only** for LD/SS (GN/TQ send no `quota`, preserving today's
  bundle response).
- **`cache_key(quota)`** — returns `availabilityCacheForQuota` for LD/SS,
  `availabilityCacheTatkal` for TQ, `availabilityCache` for GN.
- **`class_cache(train, class_code, quota)`** — already routes via `cache_key`; now
  resolves LD/SS to the per-quota cache automatically.

### `app/schemas.py`

- `BookingQuota` += `LADIES = "LD"`, `SENIOR = "SS"`.
- `TrainBetween` gains **`allowed_quotas: list[str] = []`** — confirmtkt's per-train
  `allowedQuotas`, surfaced so the UI can distinguish "quota not offered on this
  train" from "offered but sold out / no data".
- New lightweight schemas for the **lazy per-quota** train-search response (additive;
  the existing `TrainsBetweenResponse` shape is untouched). **`train_number` is NOT
  unique within one result** (confirmtkt's `enableNearby: "true"` surfaces the same
  train serving different pairs; the card already keys by
  `train_number-from_code-departure_time` — `TrainSearchResults.tsx:46`), so each row
  carries the same disambiguators so the frontend can map rows back to cards:

  ```python
  class TrainQuotaClasses(BaseModel):     # one train's classes under one quota
      train_number: str
      from_code: str                      # disambiguators matching the card's key —
      departure_time: str                 # train_number alone collides under enableNearby
      classes: list[ClassAvailability]

  class TrainsQuotaAvailabilityResponse(BaseModel):
      source: str
      destination: str
      journey_date: dt.date
      quota: BookingQuota
      trains: list[TrainQuotaClasses]
  ```

### `app/providers/base.py` (Protocol) & `app/providers/irctc/provider.py`

- **Seat-finder methods** (`get_seat_status`, `get_fare`, `get_class_options`) already
  accept `quota`; today they call `search_segment(source, destination, date)` **without**
  passing it. Change them to `search_segment(..., quota=quota)` so LD/SS hit the
  per-quota cache. `class_cache(train, class, quota)` already carries quota. No new
  methods, no signature changes on the Protocol for these.
- **New Protocol + impl method** `search_quota_availability(source, destination,
  journey_date, quota) -> list[tuple[str, str, str, list[RawClassOffer]]]`
  (train_number, from_code, departure_time, offers), built from each train's
  `availabilityCacheForQuota`, ordered by `avlClassesSorted` (reusing the existing
  `_offers` helper). `search_trains_between` (the GN+TQ bundle) is unchanged. Because
  this lands on the Protocol, the two test doubles must implement it too — see Testing.

### `app/services/train_search.py`

- `search(...)` (GN+TQ bundle) unchanged, except it now also copies
  `allowed_quotas` onto each `TrainBetween`.
- New **`search_quota(source, destination, journey_date, quota) -> TrainsQuotaAvailabilityResponse`** —
  validates the date, calls `provider.search_quota_availability`, normalises each
  `RawClassOffer` through the existing `_to_class` (parser + ranking), and carries
  `train_number`/`from_code`/`departure_time` onto each `TrainQuotaClasses` row.

### `app/routers/routes.py`

- `/api/trains-between` — unchanged (returns the GN+TQ `TrainsBetweenResponse`). Its
  docstring ("both General and Tatkal quotas") stays accurate.
- `/api/find-optimal-route` — unchanged signature; `quota: BookingQuota` now also
  accepts `LD`/`SS` (FastAPI validates against the enum). Threads straight through.
  **Update the stale inline comment** on the `quota` param (`routes.py:30`,
  `# GN | TQ; …`) to `# GN | TQ | LD | SS; …`.
- **New** `GET /api/trains-between/quota?source&destination&date&quota=LD|SS` →
  `TrainsQuotaAvailabilityResponse`. (The endpoint will accept any `BookingQuota`,
  but the frontend only calls it for LD/SS since GN/TQ arrive in the primary response.)

### Seat-finder alternatives & notes (`app/services/recommendations.py`)

- `_build_alternatives` hard-codes `for q in (BookingQuota.GENERAL, BookingQuota.TATKAL)`,
  so adding LD/SS to the enum does **not** change the Switch-Suggestion banner. This is
  the intended behaviour: a Ladies/Senior search still gets GN/TQ "better-odds"
  suggestions (those quotas hold more inventory). Left as-is.
- **Added-cost note:** once the seat-finder methods pass `quota=quota`, an LD/SS
  search's searched cell uses cache key `(src,dst,date,'LD'|'SS')` while
  `_build_alternatives` evaluates GN/TQ cells (key `(src,dst,date,None)`). So an LD/SS
  search incurs **one extra bundled upstream fetch** for the GN/TQ alternatives (still
  cheap — single-flighted + LRU-cached). When implementing, update the now-inaccurate
  "no extra requests"/"no extra upstream requests" comments in `_build_alternatives`
  (`recommendations.py:198-199`) and `_evaluate_class` (`recommendations.py:147-149`):
  they hold for GN/TQ searches but an LD/SS search adds one bundle fetch.
- `_build_recommendation` currently appends Tatkal-specific note/action text
  (`"… in Tatkal quota"`, "opens ~1 day before travel"). Generalise to a small
  per-quota message map so an LD/SS recommendation reads, e.g., "Book under the Ladies
  quota on IRCTC." (GN stays note-free; TQ keeps its window hint.)

## Frontend

### Step F1 — Unify the Train-Search quota type onto `BookingQuota` (do this FIRST)

The Train-Search surface currently uses a **separate** type
`TrainQuota = 'general' | 'tatkal'` (`client.ts:198`) whose **values differ** from the
`BookingQuota` codes (`GN`/`TQ`). This is a multi-file **value** rename
(`'general'→'GN'`, `'tatkal'→'TQ'`), not a type-annotation swap, and must land before
the dropdown/card changes or they produce TS errors:

- **`client.ts`** — delete `export type TrainQuota = 'general' | 'tatkal'` (line 198);
  use `BookingQuota` everywhere it was used. Add `{ value: 'LD', label: 'Ladies' }`
  and `{ value: 'SS', label: 'Senior Citizen' }` to `QUOTAS` (the existing
  `BookingQuota` list). `SwitchSuggestionBanner.quotaLabel` derives from `QUOTAS`, so
  new labels appear automatically.
- **`TrainSearchForm.tsx`** — delete the **local shadow** `const QUOTAS` (lines 14-17,
  values `'general'/'tatkal'`) and the `TrainQuota` import; render the shared `QUOTAS`;
  retype `quota`/`onQuotaChange` props to `BookingQuota`.
- **`TrainSearchPanel.tsx`** — `useState<TrainQuota>('general')` → `useState<BookingQuota>('GN')`.
- **`TrainSearchResults.tsx`** — retype `quota: BookingQuota`. **The header summary
  renders the quota verbatim** (`· {quota}`, line 33); map it through a label
  (`QUOTAS.find(q => q.value === quota)?.label ?? quota`, the pattern
  `SwitchSuggestionBanner.quotaLabel` already uses) so it shows "Ladies", not "LD".
- **`TrainBetweenCard.tsx`** — replace `quota === 'tatkal' ? train.tatkal : train.general`
  (line 56) and the empty-state ternary (line 124); superseded by Step F4's refactor.

### Step F2 — Quota control → dropdown (both surfaces)

- **`SearchForm.tsx` (Seat Finder):** replace the segmented quota button-group with a
  `<select>` styled via `FIELD`/`LABEL` (identical to the Class field), rendering all
  four `QUOTAS`. The quota is already a controlled search param.
- **`TrainSearchForm.tsx` (Train Search):** replace the segmented pills with the same
  `<select>`.

### Step F3 — Client types & call for lazy fetch (`client.ts`)

- Add types mirroring the backend: `TrainQuotaClasses`
  (`train_number`, `from_code`, `departure_time`, `classes`) and
  `TrainsQuotaAvailabilityResponse`.
- `TrainBetween` gains `allowed_quotas: string[]`.
- Add `searchTrainsQuotaAvailability(source, destination, date, quota, signal)`.

### Step F4 — Lazy fetch + merge (`TrainSearchPanel.tsx`)

- Holds: base `data` (GN+TQ `TrainsBetweenResponse`), active `quota: BookingQuota`,
  and a per-quota cache `Record<'LD' | 'SS', Map<string, ClassAvailability[]>>` keyed
  by the **composite** `` `${train_number}-${from_code}-${departure_time}` `` (the same
  key the card uses — `train_number` alone collides), plus a per-quota fetch state
  (`idle | loading | error`).
- `onQuotaChange(next)`: set `quota`; if `next` ∈ {LD, SS} and not cached and base
  data is loaded, call `searchTrainsQuotaAvailability`, store rows under the composite
  key. Show a brief loading state over the results while fetching; re-selecting a
  cached quota is instant. A new base search (changed src/dst/date) clears the cache.
  Requests are abortable like the existing search.

### Step F5 — Card rendering (`TrainSearchResults.tsx` + `TrainBetweenCard.tsx`)

- The panel resolves, for the active quota, the `ClassAvailability[]` per train —
  GN→`train.general`, TQ→`train.tatkal`,
  LD/SS→`` cache[quota]?.get(`${t.train_number}-${t.from_code}-${t.departure_time}`) ?? [] ``
  — and passes it down.
- **`TrainBetweenCard` props become `{ train, quota, classes, onFindSeat }`.** `classes`
  is the resolved list (the card no longer derives it from `train.general/tatkal`), but
  `quota` and `train` are **still passed** because the empty-state hint must branch on
  the active quota and `train.allowed_quotas`. (The card is *not* fully decoupled from
  quota — the earlier "decoupled" framing was wrong.)
- Empty-state hint generalised from the current Tatkal-only string into a per-quota
  map, using `train.allowed_quotas`:
  - quota not in `allowed_quotas` → "Ladies/Senior quota not offered on this train."
  - offered but empty → TQ: existing "Tatkal opens ~1 day before travel"; LD/SS/GN:
    "No availability data for this train."

## Edge cases

- **Train doesn't offer the quota** (LD/SS absent from `allowed_quotas`, or
  `availabilityCacheForQuota` empty): card shows the "not offered" hint; seat-finder
  pairs degrade to `NOT_BOOKABLE` → skipped → existing zero-recommendations UI.
- **Duplicate `train_number`** within a result (enableNearby): the composite cache key
  keeps each card's LD/SS classes distinct.
- **Booking window:** LD/SS populate in advance; TQ only ~1 day out (unchanged).
- **Abort/stale:** lazy quota fetches use the same `AbortController` discipline as the
  primary search so a quota switch or new search cancels an in-flight call.
- **Cache-key collision:** the new 4th element (`fetch_group`) in the segment cache key
  prevents GN and LD responses sharing an entry.

## Out of scope

- **Premium Tatkal** — unavailable upstream (finding #4).
- **Switch-Suggestion banner** suggesting LD/SS cross-quota swaps (kept GN/TQ-only).
- The `/api/v1/availability/2monthcalendar` endpoint — discovered during the PT hunt,
  documented here for the record, not used by this feature.

## Testing (backend; frontend has no harness, per repo convention)

Split by layer — the cache-routing internals live on `IRCTCClient`, not on the
provider double.

**A. Client/payload-level** — `tests/test_irctc_provider.py` (and
`tests/test_train_search_extraction.py`), driving `IRCTCClient` /
`IRCTCRailDataProvider` over `httpx.MockTransport`. These require **new confirmtkt
fixtures** that add an `availabilityCacheForQuota` block per class (each entry with
`availability`, `availabilityDisplayName`, `fare`, mirroring `availabilityCache`) plus
an `allowedQuotas` list on the train object — none exist today (`availabilityCacheForQuota`
appears in zero current fixtures):

1. **`search_segment` cache isolation** — a `quota=LD` call and a bundled (no-quota)
   call produce distinct segment cache keys and two distinct upstream param dicts; GN
   and TQ still share one key.
2. **`cache_key` / `class_cache` routing** — on a canned train dict, GN→`availabilityCache`,
   TQ→`availabilityCacheTatkal`, LD/SS→`availabilityCacheForQuota` (extend the existing
   `test_class_cache_selects_quota_specific_cache`).
3. **`search_quota_availability`** — builds `(train_number, from_code, departure_time,
   offers)` rows from `availabilityCacheForQuota`; **`allowed_quotas`** surfaced on
   `TrainBetween`; empty per-quota cache → empty `classes`.
4. **Update the existing single-flight test** — `test_owner_cancellation_does_not_poison_waiters`
   stubs `client._do_search = _blocking_search(source, destination, date)`; widen that
   stub to `(source, destination, date, quota=None)` since `_compute` now threads
   `quota`. (Its two no-quota calls still share one key via `fetch_group=None`.)

**B. Provider/service/route/seat-finder** — `tests/conftest.py::StubProvider` (already
keys statuses by `(source, destination, class_code, quota_code)`). **Both**
`StubProvider` (conftest.py) and `FakeRailDataProvider` (`tests/fakes.py`) must gain a
`search_quota_availability` stub, since it joins the Protocol:

5. **`search_quota`** — service normalises stubbed rows into a
   `TrainsQuotaAvailabilityResponse` (parser + ranking), carrying the row
   disambiguators.
6. **Seat finder with `quota=LD|SS`** — `get_seat_status`/`get_fare` read the per-quota
   status; recommendations build with the LD/SS note text.
7. **New route** `/api/trains-between/quota` — happy path + validation (unknown quota
   → 422).

## Implementation order (for the plan)

1. Backend enum + docstrings + client (`search_segment`/`_do_search`/`cache_key`/
   `class_cache` + annotation widening) + client-level tests (A1, A2, A4).
2. Provider `search_quota_availability` (+ both test doubles) + service `search_quota`
   + new route + tests (A3, B5, B7).
3. `allowed_quotas` surfacing + seat-finder quota threading + recommendation note
   generalisation + alternatives-comment fix + tests (B6).
4. Frontend **Step F1** (TrainQuota→BookingQuota value-rename) — its own commit, green
   build before proceeding.
5. Frontend Steps F2-F5 (dropdowns, client types/call, lazy fetch + composite-key
   merge, card refactor + empty states).
