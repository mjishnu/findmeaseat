# FindMeASeat

Finds the Indian Railways booking most likely to confirm by checking every
station-pair combination that covers your journey (booking from an earlier
station or to a later one often lands in a better quota), parsing the
availability strings, and ranking by confirmation probability minus a
distance/fare penalty.

Data is **live**: routes from erail.in and per-class availability + fare from
confirmtkt — both unofficial third-party aggregators (they rate-limit and can
change format; the app degrades gracefully and returns 503 on hard failure).

## Run it

### Docker (whole stack)

```powershell
docker compose up -d --build      # frontend on http://localhost:8080, backend on :8000
```

### Local dev

Backend (http://127.0.0.1:8000, interactive docs at /docs):

```powershell
cd backend
python -m venv .venv               # first time only
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\fastapi.exe dev app/main.py
```

Frontend (http://localhost:5173, proxies /api to the backend):

```powershell
cd frontend
npm install                        # first time only
npm run dev
```

Try a real train, e.g. **16512** (KSR Bengaluru – Kannur Express). Pick a source,
destination, journey date, and class (SL, 3A, 2A, …).

Tests (dev dependencies include pytest; they are NOT in the production image):

```powershell
cd backend
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest tests -q
```

## Architecture

```
routers → services → core (parser · pairs · ranking)
                   ↘ providers (RailDataProvider Protocol)
                        └── irctc/   ← live: erail.in + confirmtkt
```

The async `RailDataProvider` Protocol (`backend/app/providers/base.py`) is the
seam: `get_route`, `get_seat_status` (returns a RAW availability string the
parser normalizes), and `get_fare`. The service fans out one concurrent call per
covering pair and degrades gracefully — a failing pair is skipped (`pairs_skipped`
in the response), not fatal.

The live provider (`backend/app/providers/irctc/`) wraps the two endpoints with
retry/backoff, a concurrency cap, and LRU + single-flight caches. Tests use a
deterministic offline double in `backend/tests/fakes.py` (never imported by app
code) so the suite needs no network.

## Adding another data source

To swap in a different scraper, an official API, or a DB: implement the
`RailDataProvider` Protocol in a sibling package and return it from
`backend/app/dependencies.py`. Nothing else — routers, services, parser, ranking,
and the UI are provider-agnostic. The parser accepts real-world IRCTC string
variants (`AVAILABLE-0044`, `GNWL15/WL10`, `RAC 12/RAC 5`, `REGRET`, …).

Ranking constants (waitlist curve, quota factors, distance-penalty weight) are
heuristics in `backend/app/core/ranking.py` — tune them there.

Implementation plan: `docs/superpowers/plans/2026-06-12-getmeaseat-train-seat-finder.md`.
