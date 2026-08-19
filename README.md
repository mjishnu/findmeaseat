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
.venv\Scripts\python.exe -m pip install .
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

Tests:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests -q
```

## Architecture

```
HTTP ─► routers ─► services ─► domain (pure logic: pairs · ranking · dates)
                       │
                       └─► providers (RailDataProvider Protocol)
                                └── prefetched  ← reads from pre-parsed JSON via Manifests
```

The backend makes **zero** outbound HTTP calls. Instead, it returns a **Manifest**
of URLs to fetch, the browser executes them concurrently, and submits the raw
JSON back to a `/process` endpoint. This avoids rate-limiting entirely.

The async `RailDataProvider` Protocol (`backend/app/providers/base.py`) is the
seam: `get_route`, `get_seat_status` (returns a RAW availability string the
parser normalizes), `get_fare`, `get_seat_prediction`, and `get_train_classes`.
The `PreFetchedProvider` (`backend/app/providers/prefetched.py`) reads from
pre-parsed confirmtkt train dicts delivered by the browser.

Services fan out one concurrent call per covering pair and degrade gracefully — a
failing pair is skipped (`pairs_skipped` in the response), not fatal.

## Adding another data source

To swap in a different scraper, an official API, or a DB: implement the
`RailDataProvider` Protocol in a sibling module under `backend/app/providers/`.
Nothing else — routers, services, domain, and the UI are provider-agnostic. The
parser accepts real-world IRCTC string variants (`AVAILABLE-0044`, `GNWL15/WL10`,
`RAC 12/RAC 5`, `REGRET`, …).

Ranking constants (waitlist curve, cost penalty weight) are heuristics in
`backend/app/domain/ranking.py` — tune them there.
