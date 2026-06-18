# Train Search — Design Spec

**Status:** Design approved; ready for implementation plan (`writing-plans`).
**Scope:** This is **Spec 1 of 2**. It covers the new **Train Search** feature only. A
follow-up (**Spec 2: Seat-finder Quota** — a General/Tatkal toggle + a unified
best-switch banner on the existing seat-finder) is deferred to its own
spec → plan → implementation cycle after this ships. Design notes for Spec 2 are
captured at the end so they aren't lost.

---

## Goal

Add a **standalone Train Search tab** to GetMeASeat: enter From/To stations (with
autocomplete) and a date, and see every train running that leg, each with its
timings, running days, and per-class fare + availability for **both General and
Tatkal** quotas. Each result deep-links into the existing seat-finder, pre-filled.

This solves the seat-finder's current entry barrier: today a user must already
know their 5-digit train number. Train Search becomes the discovery front-end
that hands a known train into the optimizer.

## Why it's cheap (the key enabling fact)

The live provider's `IRCTCClient.search_segment(source, destination, date)` already
calls confirmtkt's `/api/v1/trains/search` and returns the full `trainList` for the
leg. A single response bundles, per train:

- timings — `departureTime`, `arrivalTime`, `duration` (minutes), `runningDays` (`"1111111"`, Mon→Sun)
- stations — `fromStnCode`/`fromStnName`, `toStnCode`/`toStnName`, `distance`, `hasPantry`
- `availabilityCache` — per-class **General** quota: a raw `availability` string (`"RLWL3/WL3"`), `fare`, `availabilityDisplayName`
- `availabilityCacheTatkal` — per-class **Tatkal** quota, same shape (populated only within ~1 day of travel; empty for distant dates, mirroring IRCTC's real Tatkal window)
- `allowedQuotas` — e.g. `['GN','TQ','SS','LD']`

So Train Search needs **no new API key** and **one upstream call**, and its
availability semantics are identical to the seat-finder because both raw strings
flow through the same `parse_availability` + `confirmation_probability`.

Verified by live probe on 2026-06-16 against NDLS→BCT (13–14 trains; General
always populated; Tatkal populated for date+1, sparse for date+2, empty 5 days
out; Senior/Ladies `availabilityCacheForQuota` came back empty — **not bundled**,
hence out of scope).

## Decision Log (read before coding)

1. **Reuse confirmtkt; do not adopt the reference's API.** The reference page
   (`refrence/`) uses `irctc-api.rajivdubey.dev/searchTrainBetweenStations`, which
   needs an API key *and* a per-class `getAvailability` fan-out (its upstream
   doesn't bundle availability). Ours does. Reusing `search_segment` also means a
   Train Search followed by a deep-link into the seat-finder shares the warm
   segment cache (60s TTL, single-flighted) — the finder's first pair call is free.

2. **Stations are static local data, not a provider concern.** Station
   autocomplete is backed by a bundled dataset (`backend/app/data/stations.json`,
   ~8k entries adapted from `refrence/stations.json` into `{code,name,city}`),
   loaded once into memory by a `StationDirectory` service and exposed at
   `GET /api/stations?q=&limit=`. It does **not** touch `RailDataProvider` (which
   stays about live rail data). Serving from the backend keeps it one source of
   truth and keeps 537 KB out of the JS bundle.

3. **Both quotas returned in one response; the toggle is client-side.** The
   endpoint takes no quota param. Each `TrainBetween` carries both `general` and
   `tatkal` class lists, so the General⇄Tatkal toggle is a pure display switch
   with **zero extra network** and an instant feel.

4. **Provider returns RAW availability strings; the service normalizes.**
   Consistent with the documented rule in `providers/base.py` ("`get_seat_status`
   returns a RAW string the parser normalizes"). The new provider method returns
   `RawTrainBetween` with raw per-class strings; `TrainSearchService` runs each
   through `parse_availability` (→ `ParsedAvailability`) and
   `confirmation_probability` (→ the same odds model as the seat-finder). Provider
   keeps **no** knowledge of parsing/ranking.

5. **Use the richer `availability` field, fall back to `availabilityDisplayName`.**
   `availability` ("RLWL3/WL3") carries the quota prefix that the parser
   understands; `availabilityDisplayName` ("WL 3") loses it. Parse the former when
   present (the existing parser already accepts the `GNWL15/WL10` grammar), else
   the latter. We show **our** computed probability, not confirmtkt's `prediction`,
   for consistency with the seat-finder.

6. **Fare hygiene: coerce `0 → None`.** Tatkal "Not Available" rows return
   `fare: 0`. The service maps a 0/missing fare to `None` so a card never renders a
   misleading "₹0".

7. **Show all offered classes, in `avlClassesSorted` order**, including
   WL/RAC/Regret — Train Search is for seeing the whole picture, not just bookable
   cells. (The seat-finder, by contrast, skips NOT_BOOKABLE pairs because it's
   optimizing.)

8. **`enableNearby` stays true** (matches the existing client). confirmtkt may
   return trains boarding at a nearby station; we display each train's actual
   `fromStnCode`/`fromStnName`, so this is informative, not confusing.

9. **No router; a client-side view toggle.** Two views don't justify
   `react-router`. `App` holds `view: 'finder' | 'search'` and a `prefill` object;
   the deep-link flips the view and seeds the form. (Trade-off: no shareable URLs —
   acceptable, trivially addable later.) Default landing stays the seat-finder to
   preserve current behavior.

10. **Date is required, defaults to today (IST), bounded by the 60-day ARP** —
    identical rules to the seat-finder (reuse `booking_day_today` / ARP window).
    Empty result set is **200 with `trains: []`** (a friendly empty state), distinct
    from a `ProviderUnavailableError` → 503.

## Architecture

Unchanged layering: `routers → services → core/providers`.

```
Train Search tab (new view)
  From/To autocomplete ──GET /api/stations?q=──► StationDirectory (in-memory dataset)
  [Search] ──GET /api/trains-between?source=&destination=&date=──► TrainSearchService
       │                                          ├─ provider.search_trains_between
       │                                          │    └─ IRCTCClient.search_segment (cached confirmtkt)
       │                                          │       → RawTrainBetween (general_offers + tatkal_offers, RAW strings)
       │                                          └─ per offer: parse_availability → confirmation_probability
       │                                             (fare 0→None) → TrainBetween{general[], tatkal[]}
       ▼
  results render; General⇄Tatkal toggle switches which array each card shows
  "Find me a seat →" ──► App.setView('finder') + prefill{train,from,to,date}
                          └─ existing /api/find-optimal-route flow (segment cache warm)
```

### Backend

- **`app/data/stations.json`** — `[{ "code", "name", "city" }, …]`, generated once
  from `refrence/stations.json` (transform `stnCode/stnName/stnCity` → `code/name/city`).
- **`app/services/stations.py`** — `StationDirectory`: loads the dataset once;
  `search(q, limit=8) -> list[Station]` ranks: exact code match → code prefix →
  name/city prefix → substring; case-insensitive; capped by `limit`. Singleton via
  a `get_station_directory()` dependency (mirrors `get_provider`).
- **`app/services/train_search.py`** — `TrainSearchService(provider)`:
  `search(source, destination, journey_date) -> TrainsBetweenResponse`. Validates
  the date (reuse the seat-finder's IST/ARP logic — factor it out of
  `recommendations.py` into a shared helper if clean, else duplicate the small
  check), calls the provider, normalizes both quota offer-lists, builds the response.
- **`app/providers/base.py`** — add to the Protocol:
  `async def search_trains_between(self, source, destination, journey_date) -> list[RawTrainBetween]`.
- **`app/providers/irctc/provider.py`** — implement it via `search_segment` +
  field extraction (helpers in `irctc/client.py`); map confirmtkt class codes to
  `TravelClass`, skipping codes the enum doesn't model; emit raw strings for both
  `availabilityCache` and `availabilityCacheTatkal`.
- **`app/routers/routes.py`** — add `GET /api/trains-between` and `GET /api/stations`.

### Frontend (Tailwind heritage-ticket system; reuse `StatusBadge`)

- **`App.tsx`** — header **nav toggle** (Seat Finder · Train Search), amber
  active-underline in the existing `rail-950` bar; renders the chosen view; passes
  `prefill` into the finder on deep-link.
- **`api/client.ts`** — add `Station`, `ClassAvailability`, `TrainBetween`,
  `TrainsBetweenResponse` types; `searchStations(q, signal)` and
  `searchTrainsBetween(source, destination, date, signal)`.
- **`components/StationAutocomplete.tsx`** — debounced (300 ms) input → `/api/stations`,
  keyboard-navigable listbox, resolves to `{code, name}`; network blips degrade to
  no-dropdown silently. Used for both From and To.
- **`components/TrainSearchForm.tsx`** — From/To autocomplete + a swap button +
  date (default today, min/max ARP) + a **General/Tatkal** segmented toggle +
  Search. Mirrors `SearchForm` field styling (`LABEL`/`FIELD` conventions).
- **`components/TrainBetweenCard.tsx`** — ticket-style card: number + name,
  from→to with times and duration, a running-days strip (`M T W T F S S`, inactive
  days dimmed), per-class fare + `StatusBadge` chips for the selected quota, a
  pantry badge; an empty selected-quota list (Tatkal, distant date) shows a subtle
  "Tatkal opens ~1 day before travel" hint. Footer: **"Find me a seat →"** deep-link
  (per-train for MVP; per-class is a trivial later extension).
  - **Deep-link prefill nuance:** carry `train_number` + the search `date`, and
    seed source/destination from **this train's own** `from_code`/`to_code` (the
    stations the card displays), NOT the user's searched From/To. Because the
    finder's selects are populated from the train's *route* (erail), seeding a
    searched code that isn't on the route (the `enableNearby` case, e.g. searched
    MMCT but the train serves CSMT) would leave the select blank. The train's own
    boarding/alighting codes are always stops on its route, so both selects fill in
    and the finder evaluates the journey that train actually offers.
- **`components/TrainSearchResults.tsx`** — list + skeleton + "No direct trains
  found between X and Y" empty state.
- **`SearchForm.tsx` refactor** — accept an optional `initial` prop; make
  source/destination/date **controlled** (seeded from `initial`) so a deep-link
  pre-fills them once the train's route loads. `travelClass` is already controlled
  in `App`.

## Contracts (new schemas in `app/schemas.py`)

```python
class Station(BaseModel):
    code: str
    name: str
    city: str

class ClassAvailability(BaseModel):
    travel_class: TravelClass
    availability: ParsedAvailability      # normalized, same as the seat-finder
    probability: float                    # our confirmation_probability
    fare: int | None                      # None when unpriced/unavailable (0 → None)

class TrainBetween(BaseModel):
    train_number: str
    train_name: str
    from_code: str
    from_name: str
    to_code: str
    to_name: str
    departure_time: str                   # "HH:MM"
    arrival_time: str                     # "HH:MM"
    duration_min: int | None
    running_days: str                     # "1111111" (Mon→Sun)
    has_pantry: bool = False
    distance_km: int | None = None
    general: list[ClassAvailability]
    tatkal: list[ClassAvailability]       # often [] for distant dates

class TrainsBetweenResponse(BaseModel):
    source: str
    destination: str
    journey_date: dt.date
    trains: list[TrainBetween]

# Provider-internal (pre-normalization; raw availability strings)
class RawClassOffer(BaseModel):
    travel_class: TravelClass
    raw_availability: str
    fare: int | None

class RawTrainBetween(BaseModel):
    train_number: str
    train_name: str
    from_code: str
    from_name: str
    to_code: str
    to_name: str
    departure_time: str
    arrival_time: str
    duration_min: int | None
    running_days: str
    has_pantry: bool
    distance_km: int | None
    general_offers: list[RawClassOffer]
    tatkal_offers: list[RawClassOffer]
```

**Endpoints**

- `GET /api/stations?q=<str, min 1>&limit=<int, default 8>` → `list[Station]`.
- `GET /api/trains-between?source=<1–5>&destination=<1–5>&date=<YYYY-MM-DD>` →
  `TrainsBetweenResponse`. 422 on malformed/past/out-of-ARP date or bad codes; 503
  on upstream failure; 200 `{trains: []}` when no direct trains.

## Error handling

- Reuse the `AppError` hierarchy + the existing handler in `main.py`. Date
  validation raises `InvalidJourneyDateError`; upstream failure surfaces as
  `ProviderUnavailableError` → 503; empty results are a normal 200.
- Frontend reuses `ApiError`, `ErrorBanner`, and the skeleton/empty-state patterns.
  Autocomplete failures are non-fatal (no dropdown, no banner).

## Testing (TDD, backend; manual frontend — matches the existing project stance)

- **Unit:** `StationDirectory.search` ranking & limit; `TrainSearchService`
  normalization (raw → parsed/probability, fare 0→None, class ordering, empty
  Tatkal, empty train list), date validation.
- **API (`TestClient`):** `/api/trains-between` happy / empty / bad-date (422) /
  upstream (503); `/api/stations` happy / short-q / limit.
- **Test double:** extend `backend/tests/fakes.py` to implement
  `search_trains_between` with canned `RawTrainBetween` data — no network, mirroring
  how the existing fake serves the seat-finder.
- Frontend verified via the dev servers (the project has no vitest at this size);
  add a manual checklist to the plan.

## Out of scope (YAGNI)

PNR status, live train status, "at station", a standalone train-schedule page, and
non-bundled quotas (Ladies/Senior — they require extra per-class upstream calls).
Per-class deep-links and shareable URLs are easy later extensions.

---

## Appendix — Spec 2 preview (Seat-finder Quota; deferred, do not build here)

> **Now superseded by the full spec:** `2026-06-17-seat-finder-quota-design.md`.
> That document is authoritative; in particular it unifies the two axes into a
> single `alternatives` (class × quota) list rather than the separate
> `quota_alternative` field sketched below. Kept here only as the originating note.

Captured so the approved design isn't lost; it gets its own spec/plan next.

- Add a `quota` (GN/TQ, default GN) param to `/api/find-optimal-route`; thread it
  through the service → provider. `get_seat_status` / `get_fare` /
  `get_class_options` and the `class_cache` helper gain a `quota` arg selecting
  `availabilityCache` vs `availabilityCacheTatkal`. Touches the Protocol + IRCTC
  provider + test fake (mechanical but cross-cutting). **Free** — the Tatkal cache
  is already in the pair responses the seat-finder fetches, exactly like
  `class_alternatives`.
- Add a General/Tatkal toggle to the seat-finder form (symmetric with Class).
- Response gains `quota_alternative` (searched class in the other quota, if
  strictly better) — the mirror of `class_alternatives`.
- Frontend: a **unified best-switch banner** replacing the standalone class banner —
  it compares `class_alternatives` + `quota_alternative` and surfaces the single
  highest-odds switch (class, quota, or both). Backend is identical regardless of
  banner styling; only the component changes.
- Tatkal is empty for distant dates → the banner simply won't fire; manually
  selecting Tatkal for a far date shows a clean "Tatkal opens ~1 day before travel"
  empty state.
