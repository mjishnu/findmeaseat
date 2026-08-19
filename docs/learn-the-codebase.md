# Learn the Codebase

A short guide to reading FindMeASeat. Read it top to bottom once; afterwards
every file should have an obvious home.

## What it does

Indian Railways hides **different quotas on different station pairs of the same
train**. A berth that is waitlisted for your exact leg may be AVAILABLE if you
book from one station earlier or to one station later. FindMeASeat checks every
pair that covers your journey (and optionally, partial pairs that cover a portion of it),
reads live availability, and ranks the bookings most likely to confirm.

Two features, two tabs:

- **Train Search** — every train on a route, with per-class fare + availability
  (the landing page).
- **Seat Finder** — for one train + leg, the best covering-pair booking to make.

Data is **live** and unofficial: routes from `erail.in`, availability + fare +
ML confirmation prediction from `confirmtkt`. No database, no auth.

## Architecture in one picture

```
HTTP ─► routers ─► services ─► domain (pure logic: pairs · ranking · dates)
                       │
                       └─► providers (RailDataProvider Protocol)
                                └── prefetched  ← reads from pre-parsed JSON via Manifests
```

The rule that makes it readable: **dependencies point one way, down.** `domain/`
is pure and imports nothing above it. Services orchestrate. The provider is the
*only* code that knows about the outside world, and it's hidden behind a
Protocol so nothing else cares where data comes from.

## Read it in this order

Backend is where all the logic lives; the frontend is a thin client over it.

### 1. The contracts — what data looks like

- [backend/app/schemas/](../backend/app/schemas/) — every Pydantic model and
  enum shared across layers. Read this first; it's the vocabulary. The package is
  split into submodules (`enums.py`, `domain.py`, `requests.py`, `responses.py`,
  `manifest.py`) with a barrel `__init__.py` that re-exports everything.
- [backend/app/providers/base.py](../backend/app/providers/base.py) — the
  `RailDataProvider` Protocol. This is the seam. Every method here is the entire
  surface a data source must implement. `get_seat_status` returns a **raw**
  availability string on purpose — parsing is the app's job, not the provider's.

### 2. The pure domain — the actual cleverness

These three files have no I/O, no framework, no provider. Read and unit-test them
in isolation.

- [backend/app/domain/pairs.py](../backend/app/domain/pairs.py) — **the trick.**
  `enumerate_pairs` returns every `(board, alight)` pair that fully
  covers `source→destination` (board at the source *or earlier*, alight at the
  destination *or later*). If `partial=True`, also includes partial-coverage
  pairs whose overlap with the user's journey meets a minimum coverage percentage.
  Validates the stations are on the route and in the right direction.
- [backend/app/domain/ranking.py](../backend/app/domain/ranking.py) — the heuristics.
  `confirmation_probability` (AVAILABLE→0.99, RAC→0.95, WAITLIST→confirmtkt's own
  prediction, no-estimate→−1) and `sort_candidates` (probability minus a concave
  penalty on the *extra fare* of a longer booking, weighted by coverage).
  **All tunable knobs live here.**
- [backend/app/domain/dates.py](../backend/app/domain/dates.py) — journey-date rules
  (IST booking day, 60-day advance reservation window). One place, shared by both
  services.

### 3. The providers — parsing & data adapters

- [backend/app/providers/parser.py](../backend/app/providers/parser.py) — turns
  the messy real-world strings (`AVAILABLE-0044`, `GNWL15/WL10`, `RAC 12/RAC 5`,
  `REGRET`, `AVAILABLE-0000`) into one `ParsedAvailability`. Case/space/hyphen/
  zero-pad insensitive; anything unrecognized degrades to `UNKNOWN` instead of
  raising.
- [backend/app/providers/client.py](../backend/app/providers/client.py) —
  URL builders for erail.in and confirmtkt APIs, plus response parsers
  (`parse_erail_header`, `parse_erail_route`). There is no HTTP client here —
  the browser does all fetching.
- [backend/app/providers/prefetched.py](../backend/app/providers/prefetched.py) —
  the `PreFetchedProvider`, the only `RailDataProvider` implementation. Reads
  availability directly from pre-parsed confirmtkt `trainList` dicts delivered
  by browser fetches or the segment cache.
- [backend/app/providers/transforms.py](../backend/app/providers/transforms.py) —
  shapes confirmtkt JSON payloads into normalized `TrainBetween` response schemas.

### 4. The services — orchestration

- [backend/app/services/recommendations/](../backend/app/services/recommendations/) —
  the Seat Finder engine, split into two files:
  - **pipeline.py** — orchestrates candidate ranking and verified response
    building. `rank_candidates` validates, enumerates pairs, evaluates each,
    sorts, and builds alternatives. `build_verified_response` re-ranks with
    live IRCTC data.
  - **evaluator.py** — evaluates individual pairs and classes. `evaluate_pair`
    fetches status/fare/prediction for one pair. `evaluate_class` fans out
    concurrently across all pairs. `build_better_alternatives` finds better
    classes. `build_recommendation` attaches human-readable notes.
- [backend/app/services/seat_finder.py](../backend/app/services/seat_finder.py) —
  the multi-phase manifest flow (manifest → fetch → verify) for the seat finder.
  Manages cache lookups, segment parsing, dead-pair tracking, and phase
  transitions.
- [backend/app/services/train_search.py](../backend/app/services/train_search.py) —
  cache + manifest lifecycle for trains-between queries.
- [backend/app/services/route.py](../backend/app/services/route.py) —
  cache + manifest lifecycle for train route resolution (header → route → cached).
- [backend/app/services/stations.py](../backend/app/services/stations.py) — the
  autocomplete directory. Static local JSON, ranked per query (exact code → code
  prefix → name prefix → city prefix → substrings → fuzzy). Not a provider concern.

### 5. The edges — routing, infrastructure, errors

- [backend/app/routers/](../backend/app/routers/) — one router per feature
  (`route.py`, `seat_finder.py`, `train_search.py`, `stations.py`), assembled
  under `/api` in `__init__.py`. All use `DecompressRoute` (in `common.py`) for
  Zstd decompression and MessagePack request body decoding. Routers are thin — they validate input
  and delegate to services.
- [backend/app/infrastructure/](../backend/app/infrastructure/) — technical
  plumbing:
  - **redis.py** — shared Redis connection pool + generic typed cache classes
    (`StringRedisCache`, `FlagRedisCache`, `HashRedisCache`).
  - **cache.py** — cache singleton instances (`RouteCache`, `TrainSearchCache`,
    `SeatFinderSegmentCache`, `DeadPairCache`) wired with domain-specific serializers
    and TTLs from `config.py`.
  - **manifest_store.py** — in-memory `ManifestStore` for the multi-phase
    manifest lifecycle. Holds `RouteManifestEntry`, `SeatFinderEntry`, and
    `TrainSearchEntry` dataclasses with TTL-based eviction.
- [backend/app/config.py](../backend/app/config.py) — centralized pydantic-settings.
  All environment variables validated at import time; if missing, the app fails
  fast at startup.
- [backend/app/exceptions.py](../backend/app/exceptions.py) — domain errors with
  HTTP status codes. Services raise these; `main.py` maps them to JSON. Note
  `ProviderUnavailableError` → 503 (upstream died) is distinct from
  `TrainNotFoundError` → 404 (train doesn't exist).
- [backend/app/main.py](../backend/app/main.py) — app assembly: CORS, the
  `AppError` handler, router include, and a lifespan hook that closes Redis on
  shutdown.

### 6. Client-Side Fetch Manifests — The Browser is the HTTP Client

To avoid backend rate-limiting, the server makes **zero** outbound HTTP calls.
Instead, the backend returns a **Manifest** of URLs to fetch, the browser
executes them concurrently, and submits the raw JSON back to a `/process`
endpoint.

- **Manifest flow**: Each feature (route, seat-finder, train-search) follows a
  multi-phase pattern: `/manifest` returns `FetchDescriptor`s → browser fetches →
  `/process` receives `FetchResult`s → service advances to the next phase or
  returns final results.
- **Caching**: Four Redis caches prevent redundant browser fetches:
  - `RouteCache` — parsed train routes (24h TTL)
  - `TrainSearchCache` — full train search results per OD pair (3h TTL)
  - `SeatFinderSegmentCache` — lean availability data per segment for seat finder (3h TTL)
  - `DeadPairCache` — pairs that yielded no results (24h TTL)

## The core algorithm, end to end

A Seat Finder request for train 16512, KSR Bengaluru (SBC) → Kannur (CAN), SL:

1. Router validates input, calls `seat_finder.create_manifest`.
2. Fetch the cached route; `enumerate_pairs` yields pairs like SBC→CAN,
   *(one stop before SBC)*→CAN, SBC→*(one stop after CAN)*, etc. If enabled,
   partial pairs covering part of the journey are also added.
3. Check segment cache for each pair. Uncached pairs get `FetchDescriptor`s
   returned to the browser.
4. Browser fetches confirmtkt data, submits back to `/process`.
5. For each pair: parse → `confirmation_probability` (using confirmtkt's
   prediction for waitlists) → `sort_candidates` (penalize extra fare, weight
   by coverage).
6. Top 10 candidates get `FetchDescriptor`s for live IRCTC verification.
7. Browser fetches live availability, submits back to `/process`.
8. Re-rank with live data overrides → respond with top 3 + "switch class"
   alternatives banner.

Failures degrade, never crash: a bad pair is skipped, an unknown string becomes
`UNKNOWN` and is dropped, a dead upstream becomes a 503.

## Frontend (thin client)

React + Vite + Tailwind. The backend does the thinking; the UI submits forms and
renders responses.

- [frontend/src/api/client.ts](../frontend/src/api/client.ts) — all fetch calls,
  TypeScript types, and the **Manifest Execution Loop**. It recursively fetches
  URLs from `/manifest`, passes them to `/process`, and pre-parses bulky
  confirmtkt responses to reduce upload size. Types mirror the schemas package.
- [frontend/src/App.tsx](../frontend/src/App.tsx) — two routes (`/train-search`,
  `/seat-finder`). Each view is URL-linkable; the Seat Finder reads its prefill
  from the query string, so a deep link auto-searches.
- [frontend/src/components/TrainSearchPanel.tsx](../frontend/src/components/TrainSearchPanel.tsx)
  — Train Search state machine. GN/TQ ship in the base response; LD/SS are
  **lazily** fetched on demand and cached. "Find seat" deep-links into the Seat
  Finder carrying *that train's own* boarding codes.
- [frontend/src/components/SeatFinderPanel.tsx](../frontend/src/components/SeatFinderPanel.tsx)
  — Seat Finder state machine. Remembers the last query so the switch banner can
  re-search in another class/quota. Manages partial coverage filters.
- Other components are presentational: `SearchForm`, `StationAutocomplete`,
  `ResultsList` / `RecommendationCard` / `ProbabilityMeter`,
  `TrainSearchResults` / `TrainBetweenCard`, the banners and skeletons.

## Where to change things

| You want to… | Go to |
| --- | --- |
| Tune ranking (waitlist curve, cost penalty) | [domain/ranking.py](../backend/app/domain/ranking.py) |
| Support a new availability string format | [providers/parser.py](../backend/app/providers/parser.py) |
| Swap the data source | Write a new `RailDataProvider` and place it in `providers/` |
| Change date / advance-window rules | [domain/dates.py](../backend/app/domain/dates.py) |
| Add an endpoint | Create a router in `routers/`, a service in `services/` |
| Add/rename a field on a response | [schemas/](../backend/app/schemas/) **and** [api/client.ts](../frontend/src/api/client.ts) |
| Change cache TTLs | [config.py](../backend/app/config.py) |
| Add a new cache | [infrastructure/cache.py](../backend/app/infrastructure/cache.py) |

## Tests

In [backend/tests/](../backend/tests/), run from `backend/`:

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```
