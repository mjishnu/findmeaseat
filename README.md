# FindMeASeat 🚂

> **Smart Indian Railways seat finder.**

FindMeASeat finds the train booking combination most likely to get you a confirmed berth. By checking every station-pair combination that covers your journey—booking from an earlier station or to a later destination often unlocks different railway quotas (e.g., General Quota, Remote Location Quota, Ladies, Senior Citizen)—it parses live availability strings and ranks combinations using a heuristic confirmation probability model with distance and fare penalties.

---

## ⚡ Key Engineering Highlights

* **Zero Outbound HTTP Manifest Pattern:** The backend makes **zero** outbound HTTP calls to third-party train data aggregators. Instead, it generates a structured **Manifest** of URLs that the user's browser executes concurrently. The browser submits the raw payloads back to a `/process` endpoint for parsing and scoring. This completely bypasses backend IP bans and server-side rate limits.
* **Binary Serialization & Compression:** Employs **MessagePack** (`msgpack` / `@msgpack/msgpack`) paired with **Zstandard** (`zstandard` / `fzstd`) compression for high-throughput, low-latency payload transfer between the backend, Redis, and the frontend.
* **Two-Tier Redis Caching:** Implements segmented route and availability caching in Redis 8 (Alpine with `volatile-lru`) to minimize redundant data requests.
* **Provider-Agnostic Protocol Seam:** The `RailDataProvider` (`backend/app/providers/base.py`) is defined via Python's structural subtyping (`typing.Protocol`), allowing data scrapers, official APIs, or mock providers to be hot-swapped without touching domain logic or routers.
* **Resilient Availability String Normalization:** Custom deterministic parser handling real-world Indian Railways status strings (`AVAILABLE-0044`, `GNWL15/WL10`, `RLWL4/WL2`, `RAC 12/RAC 5`, `REGRET`, etc.).
* **Fuzzy Station Search:** Sub-millisecond station autocomplete powered by `rapidfuzz` with prefix and station-code score boosting.

---

## 🏛 System Architecture

```
                                  ┌───────────────────────────────┐
                                  │      Client Web Browser       │
                                  │   (React + TypeScript + Vite) │
                                  └───────────┬───────────────┬───┘
                                              │               │
                            1. Request Routes │               │ 2. Concurrent Fetch
                               & Manifests    │               │    External Aggregators
                                              │               │    (confirmtkt / erail)
                                              ▼               ▼
                                 ┌─────────────────────────────────┐
                                 │       FastAPI Backend API       │
                                 │          (Python 3.14)          │
                                 └────────────┬───────────────┬────┘
                                              │               │
                  ┌───────────────────────────┴─┐           ┌─┴───────────────────────────┐
                  │       Business Domain       │           │       Infrastructure        │
                  ├─────────────────────────────┤           ├─────────────────────────────┤
                  │ • Covering-Pair Generator   │           │ • Redis 8 (Route & Segment) │
                  │ • Confirmation Probability  │           │ • Manifest In-Memory Store  │
                  │ • Fare/Distance Penalty     │           │ • Zstd + MsgPack Codecs     │
                  │ • String Availability Parser│           │ • RapidFuzz Station Index   │
                  └─────────────────────────────┘           └─────────────────────────────┘
```

---

## 🚀 Getting Started

### Option 1: Docker (Recommended)

#### Local Development (Hot Reloading)
```powershell
docker compose -f docker-compose.dev.yml up --build
```
- **Web App:** [http://localhost:8080](http://localhost:8080)
- **FastAPI Backend & Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Redis:** Port `6379`

#### Production Stack
```powershell
docker compose up -d --build
```

---

### Option 2: Local Manual Setup

#### Backend (Python 3.14+)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate            # On Linux/macOS: source .venv/bin/activate
pip install -e .
fastapi dev app/main.py --host 127.0.0.1 --port 8000
```
Interactive API documentation will be available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

#### Frontend (Node 24+)

```powershell
cd frontend
npm install
npm run dev
```
Access the development UI at [http://localhost:5173](http://localhost:5173) (Vite dev server proxies `/api` to `127.0.0.1:8000`).

---

## 📁 Repository Structure

```text
findmeaseat/
├── backend/
│   ├── app/
│   │   ├── config.py                 # Pydantic environment configuration
│   │   ├── domain/                   # Pure business logic (zero I/O dependencies)
│   │   │   ├── dates.py              # Journey date arithmetic & formatting
│   │   │   ├── pairs.py              # Station covering-pair combinatorial generator
│   │   │   └── ranking.py            # Heuristic confirmation scoring & penalties
│   │   ├── infrastructure/           # Cache & storage adapters
│   │   │   ├── cache.py              # Redis segment and route cache client
│   │   │   └── manifest_store.py     # Ephemeral in-memory manifest store
│   │   ├── providers/                # Rail data provider implementations
│   │   │   ├── base.py               # RailDataProvider Protocol seam
│   │   │   ├── irctc/                # Direct aggregator schema & parser definitions
│   │   │   └── prefetched/           # Manifest-driven JSON provider
│   │   ├── routers/                  # FastAPI routing endpoints
│   │   │   ├── route.py              # Station route & intermediate stop endpoints
│   │   │   ├── seat_finder.py        # Covering-pair seat finder endpoints
│   │   │   ├── stations.py           # Fuzzy station autocomplete
│   │   │   └── train_search.py       # Trains between stations lookup
│   │   ├── schemas/                  # Pydantic domain & manifest schemas
│   │   └── services/                 # Application workflow orchestration
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/                      # Modular API layer (HTTP, Manifest, Services)
│   │   ├── components/               # UI Components (Cards, DatePicker, Autocomplete)
│   │   ├── App.tsx                   # Main application layout & state
│   │   └── index.css                 # Tailwind CSS styles & animations
│   ├── Dockerfile
│   └── package.json
├── docker-compose.dev.yml            # Local development orchestration with volume mounts
├── docker-compose.yml                # Production deployment container definitions
└── README.md
```

---

## 🔍 How the Covering-Pair Algorithm Works

1. **Station Pair Graph Enumeration:** For a train journey between Station $S$ and Station $D$, the system extracts the full sequence of intermediate stops $[S_0, S_1, \dots, S_n]$.
2. **Covering Pairs Extraction:** Enumerates all pairs $(S_i, S_j)$ such that:
   $$i \le \text{index}(S) \quad \text{and} \quad j \ge \text{index}(D)$$
   with constraints on maximum allowable station overshoot to balance quota availability against extra fare cost.
3. **Availability & Confirmation Scoring:**
   - Available berths receive a base score of $1.0$.
   - RAC (Reservation Against Cancellation) receives high confirmation estimates adjusted by RAC queue position.
   - Waitlist (GNWL / RLWL / PQWL) values are evaluated using confirmation curves and aggregator historical percentages.
4. **Penalty Adjustments:**
   $$\text{Final Score} = P(\text{Confirmation}) - \lambda_{\text{fare}} \cdot \Delta \text{Fare} - \lambda_{\text{dist}} \cdot \Delta \text{Distance}$$
   The highest-ranking options are surfaced with actionable booking instructions (e.g., *"Book from Station A to Station D, but board at Station B"*).

---

## 🛠 Tech Stack

* **Backend:** Python 3.14, FastAPI, Pydantic v2, RapidFuzz, Redis 8, MessagePack, Zstandard, Uvicorn
* **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, Lucide React, fzstd, @msgpack/msgpack
* **DevOps:** Docker, Docker Compose, Multi-stage builds
