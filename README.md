# GetMeASeat

Finds the Indian Railways booking most likely to confirm by checking every
station-pair combination that covers your journey (booking from an earlier
station or to a later one often lands in a better quota), parsing the
availability strings, and ranking by confirmation probability minus a
distance/fare penalty.

## Run it

Backend (http://127.0.0.1:8000, interactive docs at /docs):

```powershell
cd backend
python -m venv .venv          # first time only
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\fastapi.exe dev app/main.py
```

Frontend (http://localhost:5173, proxies /api to the backend):

```powershell
cd frontend
npm install                    # first time only
npm run dev
```

Demo data: train **12345** (Demo Express), stations **A–F**. Try C → D.

Tests: `cd backend; .venv\Scripts\python.exe -m pytest tests -q`

## Architecture

```
routers → services → core (parser · pairs · ranking)
                   ↘ providers (RailDataProvider Protocol)
                        └── mock/   ← ALL fake data lives here
```

## Swapping in real data

Everything fake is isolated in `backend/app/providers/mock/`. To go live:

1. Implement the three-method `RailDataProvider` Protocol
   (`backend/app/providers/base.py`) in a sibling package, e.g.
   `backend/app/providers/irctc/`, backed by the real API or a scraper.
2. Change the one factory function in `backend/app/dependencies.py`.

Nothing else — routers, services, parser, ranking, and the UI are
provider-agnostic. The parser already accepts real-world IRCTC string
variants (`AVAILABLE-0044`, `GNWL15/WL10`, `RAC 12/RAC 5`, `REGRET`, …).

Ranking constants (waitlist curve, quota factors, distance-penalty weight)
are heuristics in `backend/app/core/ranking.py` — tune them there.

Implementation plan: `docs/superpowers/plans/2026-06-12-getmeaseat-train-seat-finder.md`.
