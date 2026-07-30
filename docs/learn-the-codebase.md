# Learn the Codebase

A short guide to reading FindMeASeat. Read it top to bottom once; afterwards
every file should have an obvious home.

## What it does

Indian Railways hides **different quotas on different station pairs of the same
train**. A berth that is waitlisted for your exact leg may be AVAILABLE if you
book from one station earlier or to one station later. FindMeASeat checks every
pair that covers your journey, reads live availability, and ranks the bookings
most likely to confirm.

Two features, two tabs:

- **Train Search** — every train on a route, with per-class fare + availability
  (the landing page).
- **Seat Finder** — for one train + leg, the best covering-pair booking to make.

Data is **live** and unofficial: routes from `erail.in`, availability + fare +
ML confirmation prediction from `confirmtkt`. No database, no auth.

## Architecture in one picture

```
HTTP ─► routers ─► services ─► core (pure logic: parser · pairs · ranking · dates)
                       │
                       └─► provider (RailDataProvider Protocol)
                                └── irctc/  ← the only live source (erail + confirmtkt)
```

The rule that makes it readable: **dependencies point one way, down.** `core/`
is pure and imports nothing above it. Services orchestrate. The provider is the
*only* code that knows about the outside world, and it's hidden behind a
Protocol so nothing else cares where data comes from.

## Read it in this order

Backend is where all the logic lives; the frontend is a thin client over it.

### 1. The contracts — what data looks like

- [backend/app/schemas.py](../backend/app/schemas.py) — every Pydantic model and
  enum shared across layers. Read this first; it's the vocabulary. Note the two
  quota enums: `Quota` (a *waitlist type*: GNWL/RLWL/…) vs `BookingQuota` (the
  quota you *book under*: GN/TQ/LD/SS).
- [backend/app/providers/base.py](../backend/app/providers/base.py) — the
  `RailDataProvider` Protocol. This is the seam. Every method here is the entire
  surface a data source must implement. `get_seat_status` returns a **raw**
  availability string on purpose — parsing is the app's job, not the provider's.

### 2. The pure core — the actual cleverness

These four files have no I/O, no framework, no provider. Read and unit-test them
in isolation.

- [backend/app/core/pairs.py](../backend/app/core/pairs.py) — **the trick.**
  `enumerate_covering_pairs` returns every `(board, alight)` pair that fully
  covers `source→destination` (board at the source *or earlier*, alight at the
  destination *or later*). Validates the stations are on the route and in the
  right direction.
- [backend/app/core/parser.py](../backend/app/core/parser.py) — turns the messy
  real-world strings (`AVAILABLE-0044`, `GNWL15/WL10`, `RAC 12/RAC 5`, `REGRET`,
  `AVAILABLE-0000`) into one `ParsedAvailability`. Case/space/hyphen/zero-pad
  insensitive; anything unrecognized degrades to `UNKNOWN` instead of raising.
- [backend/app/core/ranking.py](../backend/app/core/ranking.py) — the heuristics.
  `confirmation_probability` (AVAILABLE→0.99, RAC→0.95, WAITLIST→confirmtkt's own
  prediction, no-estimate→`None`) and `option_score` (probability minus a concave
  penalty on the *extra fare* of a longer booking). **All tunable knobs live
  here.**
- [backend/app/core/dates.py](../backend/app/core/dates.py) — journey-date rules
  (IST booking day, 60-day advance reservation window). One place, shared by both
  services.

### 3. The services — orchestration

- [backend/app/services/recommendations.py](../backend/app/services/recommendations.py)
  — the Seat Finder engine. The flow, top to bottom in `find_optimal_route`:
  1. validate date, fetch route, `enumerate_covering_pairs`.
  2. `_evaluate_class`: fan out **one concurrent call per pair**
     (`asyncio.gather`), parse each, build a `_Candidate`. A pair whose upstream
     fails is *skipped* (counted in `pairs_skipped`), never fatal.
  3. sort by `_rank_key`: **status tier first** (a seat in hand always beats a
     waitlist, even a ~100% one), then score, probability, cost, distance.
  4. take top 3, attach human-readable `action` + `notes` (e.g. "change boarding
     point on IRCTC").
  5. `_build_alternatives`: a "switch class" banner — reuses the *cached* pair
     responses, so it costs no extra network calls.
- [backend/app/services/train_search.py](../backend/app/services/train_search.py)
  — thin: ask the provider for every train on the leg, run each raw string through
  the **same** parser + ranking so Train Search reads identically to Seat Finder.
- [backend/app/services/stations.py](../backend/app/services/stations.py) — the
  autocomplete directory. Static local JSON, ranked per query (exact code → code
  prefix → name prefix → city prefix → substrings). Not a provider concern.

### 4. The edges — routing, wiring, errors

- [backend/app/routers/routes.py](../backend/app/routers/routes.py) — the five
  endpoints. FastAPI's `Query`/`Path` validators do all input validation (a bad
  train number / class / date 422s before any service runs).
- [backend/app/dependencies.py](../backend/app/dependencies.py) — **the swap
  point.** `_build_provider()` returns `IRCTCRailDataProvider()`. Change one line
  to swap data sources. The provider and station directory are lazy singletons.
- [backend/app/exceptions.py](../backend/app/exceptions.py) — domain errors with
  HTTP status codes. Services raise these; `main.py` maps them to JSON. Note
  `ProviderUnavailableError` → 503 (upstream died) is distinct from
  `TrainNotFoundError` → 404 (train doesn't exist).
- [backend/app/main.py](../backend/app/main.py) — app assembly: CORS, the
  `AppError` handler, router include, and a lifespan hook that closes the
  provider's HTTP client on shutdown.

### 5. The live provider — the only part that touches the network

- [backend/app/providers/irctc/provider.py](../backend/app/providers/irctc/provider.py)
  — a thin adapter: shapes confirmtkt JSON into the app's schemas and returns
  availability strings **unparsed**. The key efficiency: `get_seat_status`,
  `get_fare`, `get_seat_prediction`, and `get_train_classes` all read from the
  **same cached confirmtkt response** for a pair — one network call serves four
  methods.
- [backend/app/providers/irctc/client.py](../backend/app/providers/irctc/client.py)
  — the HTTP layer. The hard parts:
  - retry + backoff; raises `ProviderUnavailableError` on persistent failure.
  - **two LRU caches** (route, segment) so a whole search is cheap.
  - **single-flight**: concurrent callers for the same key share one request —
    a pair's status + fare collapse into one confirmtkt fetch.
  - a `Semaphore` caps total outbound concurrency to stay polite upstream.
  - parses erail's `~`-delimited text protocol into a route.

## The core algorithm, end to end

A Seat Finder request for train 16512, KSR Bengaluru (SBC) → Kannur (CAN), SL:

1. `routes.py` validates `^\d{5}$` and the date, calls `RecommendationService`.
2. fetch the route; `enumerate_covering_pairs` yields pairs like SBC→CAN,
   *(one stop before SBC)*→CAN, SBC→*(one stop after CAN)*, etc.
3. for each pair, concurrently: confirmtkt segment search → raw availability
   string → `parse_availability` → `confirmation_probability` (using
   confirmtkt's prediction for waitlists) → `option_score` (penalize extra fare).
4. rank: AVAILABLE/RAC pairs float to the top by tier; among waitlists, highest
   confirmation chance wins, with longer/costlier bookings nudged down.
5. respond with the top 3 + a "you could switch to 3A" alternatives banner.

Failures degrade, never crash: a bad pair is skipped, an unknown string becomes
`UNKNOWN` and is dropped, a dead upstream becomes a 503.

## Frontend (thin client)

React + Vite + Tailwind. The backend does the thinking; the UI submits forms and
renders responses.

- [frontend/src/api/client.ts](../frontend/src/api/client.ts) — all fetch calls
  and TypeScript types. **These types mirror `schemas.py` by hand** — keep the
  two in sync when you change a model.
- [frontend/src/App.tsx](../frontend/src/App.tsx) — two routes (`/train-search`,
  `/seat-finder`). Each view is URL-linkable; the Seat Finder reads its prefill
  from the query string, so a deep link auto-searches.
- [frontend/src/components/TrainSearchPanel.tsx](../frontend/src/components/TrainSearchPanel.tsx)
  — Train Search state machine. GN/TQ ship in the base response; LD/SS are
  **lazily** fetched on demand and cached. "Find seat" deep-links into the Seat
  Finder carrying *that train's own* boarding codes (not the searched ones —
  `enableNearby` can surface a train serving a nearby station).
- [frontend/src/components/SeatFinderPanel.tsx](../frontend/src/components/SeatFinderPanel.tsx)
  — Seat Finder state machine. Remembers the last query so the switch banner can
  re-search in another class/quota. Resubmits abort the stale request.
- Other components are presentational: `SearchForm`, `StationAutocomplete`,
  `ResultsList` / `RecommendationCard` / `ProbabilityMeter`,
  `TrainSearchResults` / `TrainBetweenCard`, the banners and skeletons.

## Where to change things

| You want to… | Go to |
| --- | --- |
| Tune ranking (waitlist curve, cost penalty) | [core/ranking.py](../backend/app/core/ranking.py) |
| Support a new availability string format | [core/parser.py](../backend/app/core/parser.py) |
| Swap the data source | [dependencies.py](../backend/app/dependencies.py) + a new `RailDataProvider` |
| Change date / advance-window rules | [core/dates.py](../backend/app/core/dates.py) |
| Add an endpoint | [routers/routes.py](../backend/app/routers/routes.py) |
| Add/rename a field on a response | [schemas.py](../backend/app/schemas.py) **and** [api/client.ts](../frontend/src/api/client.ts) |

## Tests

In [backend/tests/](../backend/tests/), one file per module. They use a
deterministic offline double, [backend/tests/fakes.py](../backend/tests/fakes.py)
(never imported by app code), so the suite needs no network. Run them from
`backend/` — and install `requirements-dev.txt` first, or the async tests
silently skip and the suite looks green when it isn't.
