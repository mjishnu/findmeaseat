# GetMeASeat — Train Seat Finder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI backend that finds the most-likely-to-confirm Indian Railways booking by checking every station-pair combination that covers the user's journey, plus a responsive React + Tailwind v4 UI — with all fake data isolated behind a provider interface so a real API/scraper can be swapped in later.

**Architecture:** Backend is layered: `providers/` (data source behind a `Protocol` — the mock lives in its own `providers/mock/` package, the single thing to replace later), `core/` (pure logic: availability-string parser, covering-pair enumeration, probability ranking), `services/` (orchestration), `routers/` (HTTP). Frontend is a single-page Vite + React 19 + Tailwind v4 app that talks to the backend through a dev-server proxy.

**Tech Stack (versions verified current as of 2026-06-12):** Python 3.13 · FastAPI 0.136.3 (`fastapi[standard]`, Pydantic v2) · pytest 9.0.3 · Node 22 · Vite 8 (`react-ts` template, create-vite 9) · React 19.2 · Tailwind CSS 4.3 via `@tailwindcss/vite` (CSS-first config, **no** tailwind.config.js) · TypeScript 6.

**Status:** Not started. Directory is greenfield (only `docs/` exists), not yet a git repo. Local toolchain verified: Python 3.13.7, Node v22.19.0, npm 10.9.3 — all satisfy requirements (FastAPI needs ≥3.10, Vite 8 needs Node 20.19+/22.12+).

---

## Decision Log (research-backed — read before coding)

1. **Endpoint** is `GET /api/find-optimal-route` with the user-specified query params `train_number`, `user_source`, `user_destination`, `date`. GET + query params (not body) per HTTP convention for searches; the `/api` prefix lets the Vite proxy forward without rewrites. `date` is declared as `datetime.date` — FastAPI/Pydantic coerce `YYYY-MM-DD` and auto-422 on garbage (including impossible dates like `2026-02-30`), which beats regex validation.
2. **Swap seam:** `RailDataProvider` is a `typing.Protocol` with three methods (`get_route`, `get_seat_status`, `get_fare`). The mock implementation and ALL fake values (route, fares, quota rules) live in `backend/app/providers/mock/`. Swapping to a real source = implement the Protocol in a sibling package + change one factory function in `dependencies.py`. Tests swap it via `app.dependency_overrides`.
3. **Availability string grammar** (verified against IRCTC/third-party formats): IRCTC native emits `AVAILABLE-0044` (hyphen, zero-padded) and `GNWL15/WL10` (no spaces); PNR pages/aggregators emit `AVL 44`, `GNWL 15/WL 10`. In `GNWL15/WL10` the FIRST number is the booking-time serial position; the SECOND is the current queue position — **only the second matters for confirmation probability**. Hybrids exist: `WL3/AVAILABLE` means a booking made now confirms immediately (treat as AVAILABLE). Terminal states: `REGRET`, `REGRET/WL110`, `NOT AVAILABLE`, `TRAIN DEPARTED`, `TRAIN CANCELLED`, `CHARTING DONE` — all unbookable. The parser must be case/whitespace/hyphen/zero-padding insensitive.
4. **Quota hierarchy** (why this app works at all): the train origin controls the big General quota (GNWL — best clearance odds); intermediate→destination or pairs touching a "remote location" station draw Remote Location quota (RLWL — moderate/low); intermediate→intermediate pairs share one small Pooled quota (PQWL — poor). Confirmation ordering: `AVAILABLE > RAC > GNWL > RLWL > RSWL ≈ PQWL > TQWL > RQWL`. Booking from an earlier station can therefore convert a hopeless PQWL leg into a clearable GNWL ticket.
5. **Ranking formula** (constants live in `core/ranking.py`, explicitly tunable — these are third-party heuristic priors, not official figures): `P(AVAILABLE)=0.99`, `P(RAC)=0.95`; waitlist `P = wl_curve(current_wl) × quota_factor` where `wl_curve` is piecewise-linear through `(1, 0.90), (15, 0.85), (30, 0.55), (60, 0.25), (100, 0.08)` (so a lower waitlist number always ranks higher within a quota — no banding cliffs) and `quota_factor` = GNWL 1.0 / RLWL 0.5 / RSWL 0.4 / PQWL 0.35 / TQWL 0.3 / RQWL 0.2. **Distance penalty** (fares are telescopic ⇒ concave): `score = P − 0.10 × sqrt(extra_km / user_leg_km)`, clamped at 0. An earlier origin only outranks the direct leg when its probability gain beats the penalty — exactly the "significantly better" requirement. Tie-breakers: probability desc, extra fare asc, extra km asc.
6. **Pair enumeration:** route stations indexed `0..N-1`; user boards at index `s`, alights at `d` (`s < d` required). Candidates = all `(i, j)` with `i ≤ s` and `j ≥ d` — includes the user's own pair as baseline. For the 6-station demo route and a C→D journey that is `3 × 3 = 9` pairs. Worst case is ~N²/4; no cap needed.
7. **Mandatory rider notes** (real-world rules, verified): boarding later than the ticketed origin requires changing the boarding point on IRCTC ahead of travel, otherwise the TTE can mark the passenger absent and release the berth; alighting early is allowed but the fare difference is never refunded. Every recommendation that books from an earlier station MUST carry these notes.
8. **Mock determinism:** `get_seat_status` seeds `random.Random` with `f"{train}|{src}|{dst}|{date}"` (string seeding is SHA-512-based in CPython — stable across processes). Looks random across pairs/dates, identical for repeated calls ⇒ testable without patching randomness, and the UI doesn't flicker on re-search.
9. **Stale-tutorial traps to refuse** (the #1 way this build goes wrong): Tailwind v4 has **no** `npx tailwindcss init`, **no** `tailwind.config.js`, **no** `@tailwind base/components/utilities` directives, **no** PostCSS config — it's `npm install tailwindcss @tailwindcss/vite`, the `tailwindcss()` Vite plugin, and a CSS entry of `@import "tailwindcss";` with `@theme` tokens. create-vite 9 has **no** `react-swc-ts` template (use `react-ts`; the React plugin uses Oxc now). React 19: no `forwardRef`, no `useEffect`-driven fetching for event-triggered searches (use an async submit handler + `AbortController`).
10. **Testing scope:** backend gets full pytest TDD coverage (parser, pairs, ranking, provider, service, API via `TestClient`). Frontend is verified manually through the dev servers (documented checklist in Task 13) — no vitest setup at this size; revisit if the app grows.

## File Structure

```
getmeaseat/
├── .gitignore
├── README.md                            (Task 13)
├── docs/superpowers/plans/              (this plan)
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                      # FastAPI app, CORS, exception handler
│   │   ├── dependencies.py              # provider factory — THE swap point
│   │   ├── schemas.py                   # all Pydantic models + enums
│   │   ├── exceptions.py                # AppError hierarchy → HTTP codes
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── parser.py                # availability string → ParsedAvailability
│   │   │   ├── pairs.py                 # covering-pair enumeration
│   │   │   └── ranking.py               # probability + score functions
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   └── recommendations.py       # orchestration, top-3 builder
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   └── routes.py                # /api/find-optimal-route, /api/trains/{n}
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── base.py                  # RailDataProvider Protocol
│   │       └── mock/                    # ←— ALL fake data lives here, nowhere else
│   │           ├── __init__.py
│   │           ├── fixtures.py          # route A–F, remote locations, fare table
│   │           └── provider.py          # MockRailDataProvider
│   └── tests/
│       ├── conftest.py                  # StubProvider (scriptable statuses)
│       ├── test_parser.py
│       ├── test_pairs.py
│       ├── test_ranking.py
│       ├── test_mock_provider.py
│       ├── test_recommendation_service.py
│       └── test_api.py
└── frontend/
    ├── index.html                       # fonts + title (edited from template)
    ├── vite.config.ts                   # react() + tailwindcss() + /api proxy
    └── src/
        ├── main.tsx                     # template default (imports index.css)
        ├── index.css                    # @import "tailwindcss" + @theme tokens
        ├── App.tsx                      # layout, search state machine
        ├── api/
        │   └── client.ts                # typed fetch wrappers + ApiError
        └── components/
            ├── SearchForm.tsx           # train/from/to/date + route auto-load
            ├── ResultsList.tsx          # user-leg strip + card grid
            ├── RecommendationCard.tsx   # ticket-stub card
            ├── StatusBadge.tsx          # color-coded raw status chip
            ├── ProbabilityMeter.tsx     # confirmation gauge
            ├── ErrorBanner.tsx
            └── SkeletonResults.tsx      # loading placeholders
```

**UI design direction (commit to it):** "heritage railway ticket" — warm cream paper surfaces (`paper-*`), deep railway-blue ink (`rail-*`), signal-lamp green/amber/red accents for statuses. Type: **Fraunces** (display serif) + **Archivo** (body) + **IBM Plex Mono** (`font-ticket`, for train numbers/statuses — dot-matrix ticket feel). Recommendation cards are ticket stubs: dashed perforation line with punched-hole circles, rank-1 card spans full width with an amber "BEST BET" tag. Tailwind utility classes only — the single permitted inline style is the dynamic width of the probability meter.

---

### Task 1: Repo init + backend scaffold

**Files:**
- Create: `.gitignore`
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py` (+ empty `__init__.py` in `core/`, `services/`, `routers/`, `providers/`, `providers/mock/`)
- Create: `backend/tests/` (empty dir for now)

- [ ] **Step 1: Init git and write .gitignore**

```powershell
git init
```

`.gitignore` (repo root):

```gitignore
# Python
.venv/
__pycache__/
*.pyc
.pytest_cache/

# Node
node_modules/
dist/

# OS / editor
.DS_Store
Thumbs.db
```

- [ ] **Step 2: Create the backend venv and install dependencies**

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install "fastapi[standard]==0.136.3" pytest==9.0.3
```

Expected: install succeeds; `fastapi[standard]` pulls uvicorn, httpx (needed by TestClient), and the `fastapi` CLI.

`backend/requirements.txt`:

```text
fastapi[standard]==0.136.3
pytest==9.0.3
```

- [ ] **Step 3: Create the package skeleton**

```powershell
New-Item -ItemType Directory -Force backend\app\core, backend\app\services, backend\app\routers, backend\app\providers\mock, backend\tests
'', '', '', '', '', '' | ForEach-Object -Begin { $i = 0; $dirs = 'backend\app', 'backend\app\core', 'backend\app\services', 'backend\app\routers', 'backend\app\providers', 'backend\app\providers\mock' } -Process { New-Item -ItemType File -Force "$($dirs[$i])\__init__.py" | Out-Null; $i++ }
```

(Equivalently: create an empty `__init__.py` in each of the six `app` directories by hand.)

- [ ] **Step 4: Sanity-check pytest runs**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

Expected: `no tests ran` (exit code 5 is fine — the directory is empty).

- [ ] **Step 5: Commit**

```powershell
git add .gitignore backend/requirements.txt backend/app backend/tests
git commit -m "chore: scaffold backend project"
```

### Task 2: Domain schemas + error types

**Files:**
- Create: `backend/app/schemas.py`
- Create: `backend/app/exceptions.py`
- Test: `backend/tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_schemas.py
from app.schemas import AvailabilityStatus, ParsedAvailability, Quota


def test_waitlist_label_shows_quota_and_current_position():
    parsed = ParsedAvailability(
        raw="GNWL15/WL10",
        status=AvailabilityStatus.WAITLIST,
        quota=Quota.GNWL,
        series_wl=15,
        current_wl=10,
    )
    assert parsed.label == "GNWL 10"


def test_available_label_includes_seat_count_when_known():
    with_seats = ParsedAvailability(
        raw="AVAILABLE-0044", status=AvailabilityStatus.AVAILABLE, seats=44
    )
    without = ParsedAvailability(raw="WL3/AVAILABLE", status=AvailabilityStatus.AVAILABLE)
    assert with_seats.label == "AVAILABLE (44 seats)"
    assert without.label == "AVAILABLE"


def test_rac_label():
    parsed = ParsedAvailability(
        raw="RAC 12/RAC 5", status=AvailabilityStatus.RAC, series_wl=12, current_wl=5
    )
    assert parsed.label == "RAC 5"
```

- [ ] **Step 2: Run it — expect import failure**

Run (from `backend/`): `.\.venv\Scripts\python.exe -m pytest tests/test_schemas.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas'`

- [ ] **Step 3: Implement schemas.py and exceptions.py**

```python
# backend/app/schemas.py
"""All Pydantic models and enums shared across layers."""
import datetime as dt
from enum import Enum

from pydantic import BaseModel, Field


class StationStop(BaseModel):
    code: str
    name: str
    distance_km: int = Field(ge=0, description="Cumulative distance from the train's origin")


class TrainRoute(BaseModel):
    train_number: str
    train_name: str
    stations: list[StationStop]


class AvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    RAC = "RAC"
    WAITLIST = "WAITLIST"
    NOT_BOOKABLE = "NOT_BOOKABLE"  # REGRET / NOT AVAILABLE / DEPARTED / CANCELLED / CHARTING DONE
    UNKNOWN = "UNKNOWN"


class Quota(str, Enum):
    GNWL = "GNWL"  # general — origin-controlled, best clearance odds
    RLWL = "RLWL"  # remote location
    RSWL = "RSWL"  # roadside
    PQWL = "PQWL"  # pooled — shared by many intermediate pairs
    TQWL = "TQWL"  # tatkal — cleared after GNWL at charting
    RQWL = "RQWL"  # request — last resort


class ParsedAvailability(BaseModel):
    raw: str
    status: AvailabilityStatus
    quota: Quota | None = None
    seats: int | None = None
    # For RAC strings the same two slots hold the RAC positions.
    series_wl: int | None = None   # first number: booking-time serial position
    current_wl: int | None = None  # second number: current queue position — drives ranking

    @property
    def label(self) -> str:
        if self.status is AvailabilityStatus.AVAILABLE:
            return f"AVAILABLE ({self.seats} seats)" if self.seats else "AVAILABLE"
        if self.status is AvailabilityStatus.RAC:
            return f"RAC {self.current_wl}" if self.current_wl else "RAC"
        if self.status is AvailabilityStatus.WAITLIST and self.quota:
            return f"{self.quota.value} {self.current_wl}"
        return self.raw


class UserLeg(BaseModel):
    source: str
    destination: str
    distance_km: int
    fare: int
    availability: ParsedAvailability | None = None


class Recommendation(BaseModel):
    rank: int
    book_from: str
    book_to: str
    board_at: str
    alight_at: str
    action: str
    availability: ParsedAvailability
    probability: float
    score: float
    booked_distance_km: int
    extra_km: int
    fare: int
    extra_fare: int
    requires_boarding_change: bool
    notes: list[str]


class RecommendationResponse(BaseModel):
    train_number: str
    train_name: str
    journey_date: dt.date
    user_leg: UserLeg
    pairs_evaluated: int
    recommendations: list[Recommendation]
```

```python
# backend/app/exceptions.py
"""Domain errors. main.py maps AppError subclasses to JSON responses,
so services raise these without importing anything HTTP-specific."""


class AppError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class TrainNotFoundError(AppError):
    status_code = 404

    def __init__(self, train_number: str):
        super().__init__(f"Train {train_number} not found")


class InvalidStationError(AppError):
    """Station not on route, wrong direction, or source == destination."""


class InvalidJourneyDateError(AppError):
    """Date in the past or beyond the advance reservation period."""
```

- [ ] **Step 4: Run the tests — expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_schemas.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```powershell
git add backend/app/schemas.py backend/app/exceptions.py backend/tests/test_schemas.py
git commit -m "feat: add domain schemas and error types"
```

---

### Task 3: Availability string parser

**Files:**
- Create: `backend/app/core/parser.py`
- Test: `backend/tests/test_parser.py`

- [ ] **Step 1: Write the failing test (full grammar table)**

```python
# backend/tests/test_parser.py
import pytest

from app.core.parser import parse_availability
from app.schemas import AvailabilityStatus as S
from app.schemas import Quota


@pytest.mark.parametrize(
    ("raw", "status", "quota", "seats", "series", "current"),
    [
        # AVAILABLE — IRCTC native (hyphen, zero-padded) and aggregator (spaced) forms
        ("AVAILABLE-0044", S.AVAILABLE, None, 44, None, None),
        ("AVAILABLE 10", S.AVAILABLE, None, 10, None, None),
        ("AVL 44", S.AVAILABLE, None, 44, None, None),
        ("AVAILABLE", S.AVAILABLE, None, None, None, None),
        # Hybrid: a WL series existed but booking now confirms immediately
        ("WL3/AVAILABLE", S.AVAILABLE, None, None, None, None),
        ("GNWL10/AVAILABLE", S.AVAILABLE, None, None, None, None),
        # Waitlists — spaced and unspaced, all quota types, case-insensitive
        ("GNWL15/WL10", S.WAITLIST, Quota.GNWL, None, 15, 10),
        ("GNWL 15/WL 10", S.WAITLIST, Quota.GNWL, None, 15, 10),
        ("rlwl5/wl2", S.WAITLIST, Quota.RLWL, None, 5, 2),
        ("PQWL 10/WL 8", S.WAITLIST, Quota.PQWL, None, 10, 8),
        ("TQWL4/WL4", S.WAITLIST, Quota.TQWL, None, 4, 4),
        ("WL 7", S.WAITLIST, Quota.GNWL, None, None, 7),  # bare WL ⇒ general series
        # RAC — two-number and single-number forms
        ("RAC 12/RAC 5", S.RAC, None, None, 12, 5),
        ("RAC7", S.RAC, None, None, None, 7),
        # Terminal / unbookable states
        ("REGRET", S.NOT_BOOKABLE, None, None, None, None),
        ("REGRET/WL110", S.NOT_BOOKABLE, None, None, None, None),
        ("NOT AVAILABLE", S.NOT_BOOKABLE, None, None, None, None),
        ("TRAIN DEPARTED", S.NOT_BOOKABLE, None, None, None, None),
        ("TRAIN CANCELLED", S.NOT_BOOKABLE, None, None, None, None),
        ("CHARTING DONE", S.NOT_BOOKABLE, None, None, None, None),
        # Garbage
        ("??!", S.UNKNOWN, None, None, None, None),
    ],
)
def test_parse_availability(raw, status, quota, seats, series, current):
    parsed = parse_availability(raw)
    assert parsed.status is status
    assert parsed.quota == quota
    assert parsed.seats == seats
    assert parsed.series_wl == series
    assert parsed.current_wl == current
    assert parsed.raw == raw  # original preserved for display
```

- [ ] **Step 2: Run it — expect import failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_parser.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.parser'`

- [ ] **Step 3: Implement the parser**

```python
# backend/app/core/parser.py
"""Normalize the many real-world availability string formats into one model.

IRCTC native: "AVAILABLE-0044", "GNWL15/WL10". PNR pages / aggregators:
"AVL 44", "GNWL 15/WL 10". Parsing is case-, whitespace-, hyphen- and
zero-padding-insensitive. Unrecognized input degrades to UNKNOWN rather
than raising — one weird string from a future scraper must not kill a
whole search.
"""
import re

from app.schemas import AvailabilityStatus, ParsedAvailability, Quota

_NOT_BOOKABLE_TOKENS = (
    "REGRET",
    "NOT AVAILABLE",
    "TRAIN DEPARTED",
    "TRAIN CANCELLED",
    "CHARTING DONE",
)
_AVAILABLE_RE = re.compile(r"^(?:AVAILABLE|AVL)(?:[-\s]+0*(\d+))?$")
_HYBRID_AVAILABLE_RE = re.compile(r"/\s*(?:AVAILABLE|AVL)$")
_RAC_RE = re.compile(r"^RAC\s*0*(\d+)(?:\s*/\s*RAC\s*0*(\d+))?$")
_WL_RE = re.compile(r"^(GNWL|RLWL|RSWL|PQWL|TQWL|RQWL)\s*0*(\d+)\s*/\s*WL\s*0*(\d+)$")
_BARE_WL_RE = re.compile(r"^WL\s*0*(\d+)$")


def parse_availability(raw: str) -> ParsedAvailability:
    text = re.sub(r"\s+", " ", raw.strip().upper())

    for token in _NOT_BOOKABLE_TOKENS:
        if token in text:
            return ParsedAvailability(raw=raw, status=AvailabilityStatus.NOT_BOOKABLE)

    if m := _AVAILABLE_RE.match(text):
        seats = int(m.group(1)) if m.group(1) else None
        return ParsedAvailability(raw=raw, status=AvailabilityStatus.AVAILABLE, seats=seats)

    # "WL3/AVAILABLE": the WL series exists but a booking made now confirms.
    if _HYBRID_AVAILABLE_RE.search(text):
        return ParsedAvailability(raw=raw, status=AvailabilityStatus.AVAILABLE)

    if m := _RAC_RE.match(text):
        series = int(m.group(1)) if m.group(2) else None
        current = int(m.group(2) or m.group(1))
        return ParsedAvailability(
            raw=raw, status=AvailabilityStatus.RAC, series_wl=series, current_wl=current
        )

    if m := _WL_RE.match(text):
        return ParsedAvailability(
            raw=raw,
            status=AvailabilityStatus.WAITLIST,
            quota=Quota(m.group(1)),
            series_wl=int(m.group(2)),
            current_wl=int(m.group(3)),
        )

    # Bare "WL 7" (some aggregators) — general series by convention.
    if m := _BARE_WL_RE.match(text):
        return ParsedAvailability(
            raw=raw,
            status=AvailabilityStatus.WAITLIST,
            quota=Quota.GNWL,
            current_wl=int(m.group(1)),
        )

    return ParsedAvailability(raw=raw, status=AvailabilityStatus.UNKNOWN)
```

- [ ] **Step 4: Run the tests — expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_parser.py -q`
Expected: `21 passed`

- [ ] **Step 5: Commit**

```powershell
git add backend/app/core/parser.py backend/tests/test_parser.py
git commit -m "feat: add availability string parser"
```

### Task 4: Provider Protocol + mock data package

**Files:**
- Create: `backend/app/providers/base.py`
- Create: `backend/app/providers/mock/fixtures.py`
- Create: `backend/app/providers/mock/provider.py`
- Test: `backend/tests/test_mock_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_mock_provider.py
import datetime as dt

import pytest

from app.core.parser import parse_availability
from app.providers.mock.fixtures import calculate_fare
from app.providers.mock.provider import MockRailDataProvider
from app.schemas import AvailabilityStatus, Quota

DATE = dt.date(2026, 7, 1)


@pytest.fixture()
def provider() -> MockRailDataProvider:
    return MockRailDataProvider()


def test_route_lookup(provider):
    route = provider.get_route("12345")
    assert route is not None
    assert [s.code for s in route.stations] == ["A", "B", "C", "D", "E", "F"]
    assert provider.get_route("99999") is None


def test_seat_status_is_deterministic(provider):
    first = provider.get_seat_status("12345", "C", "D", DATE)
    second = provider.get_seat_status("12345", "C", "D", DATE)
    assert first == second


def test_seat_status_is_always_parseable(provider):
    codes = ["A", "B", "C", "D", "E", "F"]
    for i, src in enumerate(codes):
        for dst in codes[i + 1 :]:
            parsed = parse_availability(provider.get_seat_status("12345", src, dst, DATE))
            assert parsed.status is not AvailabilityStatus.UNKNOWN


def test_quota_mirrors_real_mechanics(provider):
    """Origin pairs draw GNWL; remote-location/terminus pairs RLWL; the rest PQWL."""
    for day in range(1, 15):  # several dates so we hit WAITLIST draws, not just AVAILABLE
        date = dt.date(2026, 7, day)
        for src, dst, expected in [
            ("A", "D", Quota.GNWL),   # from origin
            ("B", "F", Quota.RLWL),   # to terminus
            ("C", "D", Quota.RLWL),   # D is a remote-location station
            ("B", "C", Quota.PQWL),   # intermediate → intermediate
        ]:
            parsed = parse_availability(provider.get_seat_status("12345", src, dst, date))
            if parsed.status is AvailabilityStatus.WAITLIST:
                assert parsed.quota == expected, f"{src}->{dst} on {date}"


def test_fare_is_telescopic_rounded_and_floored():
    assert calculate_fare(40) == max(105, 5 * round(40 * 1.30 / 5))  # no rebate band
    assert calculate_fare(10) == 105                                  # class minimum
    assert calculate_fare(170) == 190                                 # 170·1.30·0.85 ≈ 187.9 → 190
    assert calculate_fare(1020) < calculate_fare(510) * 2             # concave: long legs cheaper per km
    fares = [calculate_fare(km) for km in (50, 120, 310, 480, 750, 1020)]
    assert fares == sorted(fares)                                     # monotonic
    assert all(f % 5 == 0 for f in fares)                             # rounded to ₹5


def test_fare_provider_uses_route_distance(provider):
    assert provider.get_fare("12345", "C", "D") == calculate_fare(170)  # 480 − 310
```

- [ ] **Step 2: Run it — expect import failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_mock_provider.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement base.py, fixtures.py, provider.py**

```python
# backend/app/providers/base.py
"""The seam between the app and its data source."""
import datetime as dt
from typing import Protocol

from app.schemas import TrainRoute


class RailDataProvider(Protocol):
    """Interface every data source must satisfy.

    providers/mock implements this today. To go live, implement these three
    methods against the real IRCTC API / a scraper / a DB in a sibling
    package (e.g. providers/irctc/) and change one line in app/dependencies.py.
    """

    def get_route(self, train_number: str) -> TrainRoute | None: ...

    def get_seat_status(
        self, train_number: str, source: str, destination: str, journey_date: dt.date
    ) -> str: ...

    def get_fare(self, train_number: str, source: str, destination: str) -> int: ...
```

```python
# backend/app/providers/mock/fixtures.py
"""Hard-coded demo data. This `mock` package is the ONLY place fake values
live; nothing outside providers/mock/ may import from it (tests excepted)."""
from app.schemas import StationStop, TrainRoute

DEMO_TRAIN = TrainRoute(
    train_number="12345",
    train_name="Demo Express",
    stations=[
        StationStop(code="A", name="Alipore Junction", distance_km=0),
        StationStop(code="B", name="Barwadih", distance_km=120),
        StationStop(code="C", name="Chandrapur", distance_km=310),
        StationStop(code="D", name="Daund Junction", distance_km=480),
        StationStop(code="E", name="Erode Junction", distance_km=750),
        StationStop(code="F", name="Firozpur City", distance_km=1020),
    ],
)

TRAINS: dict[str, TrainRoute] = {DEMO_TRAIN.train_number: DEMO_TRAIN}

# Stations owning a Remote Location quota on this route. Real trains define
# these per timetable; pairs touching one draw RLWL instead of PQWL.
REMOTE_LOCATIONS: frozenset[str] = frozenset({"D"})

# Mock telescopic fare model: flat ₹/km discounted by total-distance slab,
# rounded to ₹5 with a class minimum — same shape as real IR fare tables.
_BASE_RATE_PER_KM = 1.30
_REBATE_SLABS: list[tuple[int, float]] = [(50, 0.0), (100, 0.05), (500, 0.15), (1000, 0.25), (1500, 0.30)]
_MAX_REBATE = 0.40
_MIN_FARE = 105


def calculate_fare(distance_km: int) -> int:
    rebate = _MAX_REBATE
    for limit, slab_rebate in _REBATE_SLABS:
        if distance_km <= limit:
            rebate = slab_rebate
            break
    fare = distance_km * _BASE_RATE_PER_KM * (1 - rebate)
    return max(_MIN_FARE, 5 * round(fare / 5))
```

```python
# backend/app/providers/mock/provider.py
"""Deterministic fake RailDataProvider.

Seeding random.Random with the full query string makes results look random
across pairs/dates but identical for repeated calls (CPython seeds str via
SHA-512, stable across processes) — so tests and re-searches are stable.
"""
import datetime as dt
import random

from app.providers.mock.fixtures import REMOTE_LOCATIONS, TRAINS, calculate_fare
from app.schemas import TrainRoute


class MockRailDataProvider:
    def get_route(self, train_number: str) -> TrainRoute | None:
        return TRAINS.get(train_number)

    def get_fare(self, train_number: str, source: str, destination: str) -> int:
        km = {s.code: s.distance_km for s in TRAINS[train_number].stations}
        return calculate_fare(abs(km[destination] - km[source]))

    def get_seat_status(
        self, train_number: str, source: str, destination: str, journey_date: dt.date
    ) -> str:
        # Assumes the service validated train/stations first.
        codes = [s.code for s in TRAINS[train_number].stations]
        i, j = codes.index(source), codes.index(destination)
        rng = random.Random(f"{train_number}|{source}|{destination}|{journey_date.isoformat()}")

        # Quota mirrors real IRCTC mechanics: the origin controls the big
        # general quota; pairs touching a remote location or the terminus
        # draw RLWL; everything else shares the small pooled quota.
        if i == 0:
            quota, p_available = "GNWL", 0.40
        elif j == len(codes) - 1 or source in REMOTE_LOCATIONS or destination in REMOTE_LOCATIONS:
            quota, p_available = "RLWL", 0.15
        else:
            quota, p_available = "PQWL", 0.10

        roll = rng.random()
        if roll < 0.08:
            return "REGRET"
        if roll < 0.08 + p_available:
            seats = rng.randint(1, 60)
            # Emit both real-world formats so the parser's normalization is exercised.
            return rng.choice([f"AVAILABLE-{seats:04d}", f"AVAILABLE {seats}"])
        series = rng.randint(2, 40)
        current = rng.randint(1, series)
        return rng.choice([f"{quota}{series}/WL{current}", f"{quota} {series}/WL {current}"])
```

- [ ] **Step 4: Run the tests — expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_mock_provider.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```powershell
git add backend/app/providers backend/tests/test_mock_provider.py
git commit -m "feat: add mock rail data provider behind Protocol seam"
```

---

### Task 5: Covering-pair enumeration

**Files:**
- Create: `backend/app/core/pairs.py`
- Test: `backend/tests/test_pairs.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_pairs.py
import pytest

from app.core.pairs import enumerate_covering_pairs
from app.exceptions import InvalidStationError
from app.providers.mock.fixtures import DEMO_TRAIN


def test_c_to_d_yields_all_nine_covering_pairs():
    pairs = enumerate_covering_pairs(DEMO_TRAIN, "C", "D")
    legs = {(b.code, a.code) for b, a in pairs}
    assert legs == {
        ("A", "D"), ("A", "E"), ("A", "F"),
        ("B", "D"), ("B", "E"), ("B", "F"),
        ("C", "D"), ("C", "E"), ("C", "F"),
    }


def test_every_pair_fully_covers_the_user_leg():
    codes = [s.code for s in DEMO_TRAIN.stations]
    for board, alight in enumerate_covering_pairs(DEMO_TRAIN, "B", "E"):
        assert codes.index(board.code) <= codes.index("B")
        assert codes.index(alight.code) >= codes.index("E")


def test_full_route_journey_yields_single_pair():
    pairs = enumerate_covering_pairs(DEMO_TRAIN, "A", "F")
    assert [(b.code, a.code) for b, a in pairs] == [("A", "F")]


def test_unknown_station_rejected():
    with pytest.raises(InvalidStationError, match="not on this train's route"):
        enumerate_covering_pairs(DEMO_TRAIN, "Z", "D")


def test_wrong_direction_rejected():
    with pytest.raises(InvalidStationError, match="comes after"):
        enumerate_covering_pairs(DEMO_TRAIN, "D", "C")


def test_same_station_rejected():
    with pytest.raises(InvalidStationError, match="same station"):
        enumerate_covering_pairs(DEMO_TRAIN, "C", "C")
```

- [ ] **Step 2: Run it — expect import failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_pairs.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.pairs'`

- [ ] **Step 3: Implement pairs.py**

```python
# backend/app/core/pairs.py
from app.exceptions import InvalidStationError
from app.schemas import StationStop, TrainRoute


def enumerate_covering_pairs(
    route: TrainRoute, source: str, destination: str
) -> list[tuple[StationStop, StationStop]]:
    """All (board, alight) pairs whose segment fully covers source→destination.

    Booking from an earlier station and/or to a later one is the whole trick:
    those pairs draw on different — often better — quotas. Pairs that do not
    cover the full user leg are never generated.
    """
    codes = [stop.code for stop in route.stations]
    route_str = " → ".join(codes)
    if source not in codes:
        raise InvalidStationError(f"Station {source} is not on this train's route ({route_str})")
    if destination not in codes:
        raise InvalidStationError(
            f"Station {destination} is not on this train's route ({route_str})"
        )
    s, d = codes.index(source), codes.index(destination)
    if s == d:
        raise InvalidStationError("Source and destination are the same station")
    if s > d:
        raise InvalidStationError(
            f"{source} comes after {destination} on this route — check the direction of travel"
        )
    return [
        (route.stations[i], route.stations[j])
        for i in range(s + 1)           # board at the source or any earlier stop
        for j in range(d, len(codes))   # alight at the destination or any later stop
    ]
```

- [ ] **Step 4: Run the tests — expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_pairs.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```powershell
git add backend/app/core/pairs.py backend/tests/test_pairs.py
git commit -m "feat: add covering-pair enumeration"
```

### Task 6: Confirmation-probability ranking engine

**Files:**
- Create: `backend/app/core/ranking.py`
- Test: `backend/tests/test_ranking.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_ranking.py
import pytest

from app.core.ranking import confirmation_probability, option_score
from app.schemas import AvailabilityStatus as S
from app.schemas import ParsedAvailability, Quota


def _wl(quota: Quota, current: int) -> ParsedAvailability:
    return ParsedAvailability(
        raw="x", status=S.WAITLIST, quota=quota, series_wl=current, current_wl=current
    )


def _status(status: S, **kw) -> ParsedAvailability:
    return ParsedAvailability(raw="x", status=status, **kw)


def test_priority_hierarchy_available_gnwl_rlwl_pqwl():
    available = confirmation_probability(_status(S.AVAILABLE, seats=5))
    rac = confirmation_probability(_status(S.RAC, current_wl=3))
    gnwl = confirmation_probability(_wl(Quota.GNWL, 5))
    rlwl = confirmation_probability(_wl(Quota.RLWL, 5))
    pqwl = confirmation_probability(_wl(Quota.PQWL, 5))
    assert available > rac > gnwl > rlwl > pqwl > 0


def test_same_quota_lower_waitlist_ranks_higher():
    assert confirmation_probability(_wl(Quota.GNWL, 2)) > confirmation_probability(
        _wl(Quota.GNWL, 10)
    )
    # Strictly monotonic across the whole curve — no banding cliffs
    probs = [confirmation_probability(_wl(Quota.GNWL, wl)) for wl in (1, 8, 15, 25, 45, 80, 150)]
    assert probs == sorted(probs, reverse=True)


def test_unbookable_statuses_score_zero():
    assert confirmation_probability(_status(S.NOT_BOOKABLE)) == 0.0
    assert confirmation_probability(_status(S.UNKNOWN)) == 0.0


def test_no_penalty_for_exact_leg():
    assert option_score(0.85, extra_km=0, user_leg_km=170) == 0.85


def test_distance_penalty_grows_concavely():
    base = 0.85
    near = option_score(base, extra_km=170, user_leg_km=170)    # 2× distance booked
    far = option_score(base, extra_km=680, user_leg_km=170)     # 5× distance booked
    assert base > near > far
    # Concave: quadrupling the extra distance only doubles the penalty (sqrt)
    assert (base - far) == pytest.approx(2 * (base - near))


def test_earlier_origin_wins_only_when_significantly_better():
    # GNWL 5 booked 310 km early still beats RLWL 2 on the exact leg…
    gnwl_early = option_score(
        confirmation_probability(_wl(Quota.GNWL, 5)), extra_km=310, user_leg_km=170
    )
    rlwl_exact = option_score(
        confirmation_probability(_wl(Quota.RLWL, 2)), extra_km=0, user_leg_km=170
    )
    assert gnwl_early > rlwl_exact
    # …but a marginal same-quota improvement does NOT justify the distance cost.
    gnwl_far = option_score(
        confirmation_probability(_wl(Quota.GNWL, 8)), extra_km=850, user_leg_km=170
    )
    gnwl_exact = option_score(
        confirmation_probability(_wl(Quota.GNWL, 10)), extra_km=0, user_leg_km=170
    )
    assert gnwl_exact > gnwl_far


def test_score_clamped_at_zero():
    assert option_score(0.05, extra_km=8000, user_leg_km=100) == 0.0
```

- [ ] **Step 2: Run it — expect import failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ranking.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.ranking'`

- [ ] **Step 3: Implement ranking.py**

```python
# backend/app/core/ranking.py
"""Confirmation-probability heuristics and the distance-penalized score.

The numbers are PRIORS distilled from public waitlist-clearance patterns
(ConfirmTkt-style bands), not official figures — they are named constants
precisely so they can be tuned or replaced by a learned model later.
"""
import math

from app.schemas import AvailabilityStatus, ParsedAvailability, Quota

P_AVAILABLE = 0.99
P_RAC = 0.95  # RAC guarantees travel (shared berth) — better than every waitlist

# Piecewise-linear curve over the CURRENT waitlist number (the second number
# in "GNWL15/WL10"). Linear interpolation keeps ranking strictly monotonic:
# a lower waitlist number always scores higher within the same quota.
_WL_CURVE: list[tuple[int, float]] = [(1, 0.90), (15, 0.85), (30, 0.55), (60, 0.25), (100, 0.08)]

# Relative clearance odds by quota type. GNWL clears from the whole train's
# cancellation pool; RLWL from one remote-location quota; PQWL from a single
# pooled quota shared by many station pairs; RQWL is the last resort.
QUOTA_FACTOR: dict[Quota, float] = {
    Quota.GNWL: 1.0,
    Quota.RLWL: 0.5,
    Quota.RSWL: 0.4,
    Quota.PQWL: 0.35,
    Quota.TQWL: 0.3,
    Quota.RQWL: 0.2,
}

# Weight of the telescopic-fare distance penalty in option_score.
DISTANCE_PENALTY_WEIGHT = 0.10


def _wl_probability(current_wl: int) -> float:
    points = _WL_CURVE
    if current_wl <= points[0][0]:
        return points[0][1]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if current_wl <= x2:
            return y1 + (y2 - y1) * (current_wl - x1) / (x2 - x1)
    return points[-1][1]


def confirmation_probability(parsed: ParsedAvailability) -> float:
    """Probability that booking this status ends in a confirmed (or RAC) berth."""
    if parsed.status is AvailabilityStatus.AVAILABLE:
        return P_AVAILABLE
    if parsed.status is AvailabilityStatus.RAC:
        return P_RAC
    if parsed.status is AvailabilityStatus.WAITLIST and parsed.quota and parsed.current_wl:
        return _wl_probability(parsed.current_wl) * QUOTA_FACTOR[parsed.quota]
    return 0.0  # NOT_BOOKABLE / UNKNOWN / malformed waitlist


def option_score(probability: float, extra_km: int, user_leg_km: int) -> float:
    """Probability minus a concave distance penalty.

    Fares are telescopic (per-km rate falls with distance), so the cost of
    booking a longer leg grows sub-linearly — sqrt mirrors that. The penalty
    means an earlier origin only outranks the exact leg when it brings a
    SIGNIFICANTLY better confirmation chance.
    """
    if extra_km <= 0:
        return probability
    penalty = DISTANCE_PENALTY_WEIGHT * math.sqrt(extra_km / user_leg_km)
    return max(0.0, probability - penalty)
```

- [ ] **Step 4: Run the tests — expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ranking.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```powershell
git add backend/app/core/ranking.py backend/tests/test_ranking.py
git commit -m "feat: add confirmation ranking engine"
```

---

### Task 7: Recommendation service (orchestration)

**Files:**
- Create: `backend/app/services/recommendations.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_recommendation_service.py`

- [ ] **Step 1: Write the scriptable StubProvider shared by service and API tests**

```python
# backend/tests/conftest.py
"""Shared test doubles. StubProvider satisfies RailDataProvider structurally
and lets each test script exact availability strings per station pair."""
import datetime as dt

from app.providers.mock.fixtures import DEMO_TRAIN, calculate_fare
from app.schemas import TrainRoute


class StubProvider:
    def __init__(self, statuses: dict[tuple[str, str], str]):
        self._statuses = statuses

    def get_route(self, train_number: str) -> TrainRoute | None:
        return DEMO_TRAIN if train_number == DEMO_TRAIN.train_number else None

    def get_seat_status(
        self, train_number: str, source: str, destination: str, journey_date: dt.date
    ) -> str:
        return self._statuses.get((source, destination), "REGRET")

    def get_fare(self, train_number: str, source: str, destination: str) -> int:
        km = {s.code: s.distance_km for s in DEMO_TRAIN.stations}
        return calculate_fare(abs(km[destination] - km[source]))


def tomorrow() -> dt.date:
    return dt.date.today() + dt.timedelta(days=1)
```

- [ ] **Step 2: Write the failing service tests**

```python
# backend/tests/test_recommendation_service.py
import datetime as dt

import pytest

from app.exceptions import InvalidJourneyDateError, InvalidStationError, TrainNotFoundError
from app.services.recommendations import RecommendationService
from tests.conftest import StubProvider, tomorrow

# Hand-computed expectation (see Decision Log #5):
#   A→F AVAILABLE: 0.99 − 0.10·√(850/170) ≈ 0.766
#   A→D GNWL wl10: 0.868 − 0.10·√(310/170) ≈ 0.733
#   C→D PQWL wl8:  0.875 × 0.35           ≈ 0.306
STATUSES = {
    ("C", "D"): "PQWL 10/WL 8",
    ("A", "D"): "GNWL 15/WL 10",
    ("A", "F"): "AVAILABLE 10",
}


@pytest.fixture()
def service() -> RecommendationService:
    return RecommendationService(StubProvider(STATUSES))


def test_ranks_better_quota_from_earlier_station_first(service):
    res = service.find_optimal_route("12345", "C", "D", tomorrow())
    legs = [(r.book_from, r.book_to) for r in res.recommendations]
    assert legs == [("A", "F"), ("A", "D"), ("C", "D")]
    assert [r.rank for r in res.recommendations] == [1, 2, 3]
    scores = [r.score for r in res.recommendations]
    assert scores == sorted(scores, reverse=True)


def test_action_strings_explain_the_booking(service):
    res = service.find_optimal_route("12345", "C", "D", tomorrow())
    by_leg = {(r.book_from, r.book_to): r for r in res.recommendations}
    assert (
        by_leg[("A", "F")].action
        == "Book A to F, board at C, alight at D. Status: AVAILABLE (10 seats)"
    )
    assert by_leg[("A", "D")].action == "Book A to D, board at C. Status: GNWL 10"
    assert by_leg[("C", "D")].action == "Book C to D, board at C. Status: PQWL 8"


def test_boarding_change_and_refund_notes(service):
    res = service.find_optimal_route("12345", "C", "D", tomorrow())
    early = next(r for r in res.recommendations if r.book_from == "A" and r.book_to == "D")
    assert early.requires_boarding_change is True
    assert any("boarding point" in n.lower() for n in early.notes)
    assert any("not refundable" in n.lower() for n in early.notes)
    exact = next(r for r in res.recommendations if (r.book_from, r.book_to) == ("C", "D"))
    assert exact.requires_boarding_change is False
    assert exact.extra_km == 0 and exact.extra_fare == 0


def test_user_leg_echoes_baseline_status(service):
    res = service.find_optimal_route("12345", "C", "D", tomorrow())
    assert res.user_leg.availability is not None
    assert res.user_leg.availability.raw == "PQWL 10/WL 8"
    assert res.user_leg.distance_km == 170
    assert res.pairs_evaluated == 9


def test_at_most_three_recommendations():
    everything_open = {
        (s, d): "AVAILABLE 5"
        for s in "ABC"
        for d in "DEF"
    }
    service = RecommendationService(StubProvider(everything_open))
    res = service.find_optimal_route("12345", "C", "D", tomorrow())
    assert len(res.recommendations) == 3


def test_unbookable_pairs_are_excluded():
    service = RecommendationService(StubProvider({}))  # every pair → REGRET
    res = service.find_optimal_route("12345", "C", "D", tomorrow())
    assert res.recommendations == []


def test_unknown_train_raises(service):
    with pytest.raises(TrainNotFoundError):
        service.find_optimal_route("99999", "C", "D", tomorrow())


def test_invalid_station_raises(service):
    with pytest.raises(InvalidStationError):
        service.find_optimal_route("12345", "C", "Q", tomorrow())


def test_station_input_is_normalized(service):
    res = service.find_optimal_route("12345", " c ", "d", tomorrow())
    assert res.user_leg.source == "C" and res.user_leg.destination == "D"


def test_past_and_far_future_dates_rejected(service):
    with pytest.raises(InvalidJourneyDateError, match="past"):
        service.find_optimal_route("12345", "C", "D", dt.date.today() - dt.timedelta(days=1))
    with pytest.raises(InvalidJourneyDateError, match="advance reservation"):
        service.find_optimal_route("12345", "C", "D", dt.date.today() + dt.timedelta(days=61))
```

- [ ] **Step 3: Run it — expect import failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.recommendations'`

- [ ] **Step 4: Implement the service**

```python
# backend/app/services/recommendations.py
"""Orchestrates a search: enumerate covering pairs, fetch + parse each
status, rank, and build the top-3 response with human-readable actions."""
import datetime as dt
from dataclasses import dataclass

from app.core.pairs import enumerate_covering_pairs
from app.core.parser import parse_availability
from app.core.ranking import confirmation_probability, option_score
from app.exceptions import InvalidJourneyDateError, TrainNotFoundError
from app.providers.base import RailDataProvider
from app.schemas import (
    AvailabilityStatus,
    ParsedAvailability,
    Recommendation,
    RecommendationResponse,
    StationStop,
    UserLeg,
)

MAX_RECOMMENDATIONS = 3
ADVANCE_RESERVATION_DAYS = 60  # IRCTC ARP, 60 days excluding journey date (since Nov 2024)


@dataclass
class _Candidate:
    board: StationStop
    alight: StationStop
    parsed: ParsedAvailability
    probability: float
    score: float
    booked_km: int
    extra_km: int
    fare: int
    extra_fare: int


class RecommendationService:
    def __init__(self, provider: RailDataProvider) -> None:
        self._provider = provider

    def find_optimal_route(
        self,
        train_number: str,
        user_source: str,
        user_destination: str,
        journey_date: dt.date,
    ) -> RecommendationResponse:
        source = user_source.strip().upper()
        destination = user_destination.strip().upper()
        self._validate_date(journey_date)

        route = self._provider.get_route(train_number)
        if route is None:
            raise TrainNotFoundError(train_number)

        pairs = enumerate_covering_pairs(route, source, destination)
        km = {stop.code: stop.distance_km for stop in route.stations}
        user_leg_km = km[destination] - km[source]
        user_leg_fare = self._provider.get_fare(train_number, source, destination)

        candidates: list[_Candidate] = []
        user_leg_parsed: ParsedAvailability | None = None
        for board, alight in pairs:
            raw = self._provider.get_seat_status(train_number, board.code, alight.code, journey_date)
            parsed = parse_availability(raw)
            if board.code == source and alight.code == destination:
                user_leg_parsed = parsed
            if parsed.status in (AvailabilityStatus.NOT_BOOKABLE, AvailabilityStatus.UNKNOWN):
                continue
            booked_km = km[alight.code] - km[board.code]
            extra_km = booked_km - user_leg_km
            fare = self._provider.get_fare(train_number, board.code, alight.code)
            probability = confirmation_probability(parsed)
            candidates.append(
                _Candidate(
                    board=board,
                    alight=alight,
                    parsed=parsed,
                    probability=probability,
                    score=option_score(probability, extra_km, user_leg_km),
                    booked_km=booked_km,
                    extra_km=extra_km,
                    fare=fare,
                    extra_fare=fare - user_leg_fare,
                )
            )

        # Best score first; ties: higher raw probability, cheaper, shorter.
        candidates.sort(key=lambda c: (-c.score, -c.probability, c.extra_fare, c.extra_km))

        recommendations = [
            self._build_recommendation(rank, cand, source, destination)
            for rank, cand in enumerate(candidates[:MAX_RECOMMENDATIONS], start=1)
        ]
        return RecommendationResponse(
            train_number=route.train_number,
            train_name=route.train_name,
            journey_date=journey_date,
            user_leg=UserLeg(
                source=source,
                destination=destination,
                distance_km=user_leg_km,
                fare=user_leg_fare,
                availability=user_leg_parsed,
            ),
            pairs_evaluated=len(pairs),
            recommendations=recommendations,
        )

    def _validate_date(self, journey_date: dt.date) -> None:
        today = dt.date.today()
        if journey_date < today:
            raise InvalidJourneyDateError("Journey date is in the past")
        if journey_date > today + dt.timedelta(days=ADVANCE_RESERVATION_DAYS):
            raise InvalidJourneyDateError(
                f"Journey date is outside the {ADVANCE_RESERVATION_DAYS}-day advance reservation period"
            )

    def _build_recommendation(
        self, rank: int, cand: _Candidate, source: str, destination: str
    ) -> Recommendation:
        requires_change = cand.board.code != source
        notes: list[str] = []
        if requires_change:
            notes.append(
                f"Change the boarding point to {source} on IRCTC immediately after booking — "
                "without it the TTE can mark you absent and release the berth."
            )
        if cand.extra_fare > 0:
            notes.append(
                f"Costs ₹{cand.extra_fare} more than the direct {source}→{destination} fare; "
                "the unused distance is not refundable."
            )
        if cand.alight.code != destination:
            notes.append(
                f"Get off at {destination}; the ticket runs on to {cand.alight.code} "
                "but the difference is not refunded."
            )

        action = f"Book {cand.board.code} to {cand.alight.code}, board at {source}"
        if cand.alight.code != destination:
            action += f", alight at {destination}"
        action += f". Status: {cand.parsed.label}"

        return Recommendation(
            rank=rank,
            book_from=cand.board.code,
            book_to=cand.alight.code,
            board_at=source,
            alight_at=destination,
            action=action,
            availability=cand.parsed,
            probability=round(cand.probability, 3),
            score=round(cand.score, 3),
            booked_distance_km=cand.booked_km,
            extra_km=cand.extra_km,
            fare=cand.fare,
            extra_fare=cand.extra_fare,
            requires_boarding_change=requires_change,
            notes=notes,
        )
```

- [ ] **Step 5: Run the tests — expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_service.py -q`
Expected: `10 passed`

- [ ] **Step 6: Commit**

```powershell
git add backend/app/services backend/tests/conftest.py backend/tests/test_recommendation_service.py
git commit -m "feat: add recommendation service"
```

### Task 8: HTTP API layer

**Files:**
- Create: `backend/app/dependencies.py`
- Create: `backend/app/routers/routes.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write the failing API tests**

```python
# backend/tests/test_api.py
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_provider
from app.main import app
from tests.conftest import StubProvider, tomorrow

STATUSES = {
    ("C", "D"): "PQWL 10/WL 8",
    ("A", "D"): "GNWL 15/WL 10",
    ("A", "F"): "AVAILABLE 10",
}

client = TestClient(app)


@pytest.fixture()
def stubbed():
    app.dependency_overrides[get_provider] = lambda: StubProvider(STATUSES)
    yield
    app.dependency_overrides.clear()


def _search(**overrides) -> dict:
    params = {
        "train_number": "12345",
        "user_source": "C",
        "user_destination": "D",
        "date": tomorrow().isoformat(),
    } | overrides
    return {"params": params}


def test_happy_path_returns_ranked_recommendations(stubbed):
    res = client.get("/api/find-optimal-route", **_search())
    assert res.status_code == 200
    body = res.json()
    assert body["train_name"] == "Demo Express"
    assert body["pairs_evaluated"] == 9
    legs = [(r["book_from"], r["book_to"]) for r in body["recommendations"]]
    assert legs == [["A", "F"], ["A", "D"], ["C", "D"]] or legs == [("A", "F"), ("A", "D"), ("C", "D")]
    top = body["recommendations"][0]
    assert top["action"].startswith("Book A to F, board at C")
    assert top["requires_boarding_change"] is True
    assert top["availability"]["status"] == "AVAILABLE"


def test_works_with_real_mock_provider_end_to_end():
    # No override: exercises MockRailDataProvider through the full stack.
    res = client.get("/api/find-optimal-route", **_search())
    assert res.status_code == 200
    body = res.json()
    assert body["pairs_evaluated"] == 9
    scores = [r["score"] for r in body["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    assert len(body["recommendations"]) <= 3


def test_unknown_train_404(stubbed):
    res = client.get("/api/find-optimal-route", **_search(train_number="99999"))
    assert res.status_code == 404
    assert "99999" in res.json()["detail"]


def test_invalid_station_400(stubbed):
    res = client.get("/api/find-optimal-route", **_search(user_source="Z"))
    assert res.status_code == 400
    assert "not on this train's route" in res.json()["detail"]


def test_reversed_direction_400(stubbed):
    res = client.get("/api/find-optimal-route", **_search(user_source="D", user_destination="C"))
    assert res.status_code == 400


def test_past_date_400(stubbed):
    res = client.get(
        "/api/find-optimal-route",
        **_search(date=(dt.date.today() - dt.timedelta(days=1)).isoformat()),
    )
    assert res.status_code == 400


def test_malformed_date_422(stubbed):
    res = client.get("/api/find-optimal-route", **_search(date="2026-13-99"))
    assert res.status_code == 422


def test_malformed_train_number_422(stubbed):
    res = client.get("/api/find-optimal-route", **_search(train_number="12AB5"))
    assert res.status_code == 422


def test_train_route_endpoint(stubbed):
    res = client.get("/api/trains/12345")
    assert res.status_code == 200
    assert [s["code"] for s in res.json()["stations"]] == ["A", "B", "C", "D", "E", "F"]
    assert client.get("/api/trains/99999").status_code == 404
```

- [ ] **Step 2: Run it — expect import failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_api.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.dependencies'`

- [ ] **Step 3: Implement dependencies.py, routes.py, main.py**

```python
# backend/app/dependencies.py
from typing import Annotated

from fastapi import Depends

from app.providers.base import RailDataProvider
from app.providers.mock.provider import MockRailDataProvider

_provider = MockRailDataProvider()


def get_provider() -> RailDataProvider:
    # THE swap point: return your real provider here when it exists.
    # Tests substitute it via app.dependency_overrides[get_provider].
    return _provider


ProviderDep = Annotated[RailDataProvider, Depends(get_provider)]
```

```python
# backend/app/routers/routes.py
import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import ProviderDep
from app.exceptions import TrainNotFoundError
from app.schemas import RecommendationResponse, TrainRoute
from app.services.recommendations import RecommendationService

router = APIRouter(prefix="/api")


@router.get("/find-optimal-route", response_model=RecommendationResponse)
def find_optimal_route(
    provider: ProviderDep,
    train_number: Annotated[str, Query(pattern=r"^\d{5}$", description="5-digit train number")],
    user_source: Annotated[str, Query(min_length=1, max_length=5)],
    user_destination: Annotated[str, Query(min_length=1, max_length=5)],
    date: dt.date,  # FastAPI coerces YYYY-MM-DD and 422s on malformed/impossible dates
) -> RecommendationResponse:
    return RecommendationService(provider).find_optimal_route(
        train_number, user_source, user_destination, date
    )


@router.get("/trains/{train_number}", response_model=TrainRoute)
def get_train(train_number: str, provider: ProviderDep) -> TrainRoute:
    """Route lookup for UI dropdowns."""
    route = provider.get_route(train_number)
    if route is None:
        raise TrainNotFoundError(train_number)
    return route
```

```python
# backend/app/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.exceptions import AppError
from app.routers.routes import router

app = FastAPI(
    title="GetMeASeat API",
    version="0.1.0",
    description="Finds the booking combination most likely to confirm by "
    "checking every station pair that covers the user's journey.",
)

# The Vite dev proxy makes CORS unnecessary in dev, but explicit origins keep
# the API usable when the frontend is pointed straight at :8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(router)
```

- [ ] **Step 4: Run the whole backend suite — expect pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests -q`
Expected: `53 passed` (3 schemas + 21 parser + 6 provider + 6 pairs + 7 ranking + 10 service + 9 API; count may differ by a couple if parametrize cases were adjusted — all green is the requirement)

- [ ] **Step 5: Smoke-test the live server**

```powershell
# from backend/ — starts on http://127.0.0.1:8000, docs at /docs
.\.venv\Scripts\fastapi.exe dev app/main.py
```

In a second terminal:

```powershell
$date = (Get-Date).AddDays(7).ToString('yyyy-MM-dd')
Invoke-RestMethod "http://127.0.0.1:8000/api/find-optimal-route?train_number=12345&user_source=C&user_destination=D&date=$date" | ConvertTo-Json -Depth 6
```

Expected: JSON with `train_name: Demo Express`, `pairs_evaluated: 9`, up to 3 `recommendations`, each with an `action` like `"Book A to D, board at C. Status: GNWL 7"` and descending `score`s. Stop the server afterwards.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/dependencies.py backend/app/routers backend/app/main.py backend/tests/test_api.py
git commit -m "feat: expose find-optimal-route HTTP API"
```

### Task 9: Frontend scaffold — Vite 8 + React 19 + Tailwind v4

Frontend tasks have no automated tests (see Decision Log #10); each ends with a concrete browser/build verification instead.

**Files:**
- Create: `frontend/` (via create-vite `react-ts` template)
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/index.html`
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/App.tsx` (placeholder for now)
- Delete: `frontend/src/App.css`, `frontend/src/assets/react.svg`

- [ ] **Step 1: Scaffold and install (note the extra `--` before `--template`)**

```powershell
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install tailwindcss @tailwindcss/vite
```

Do **NOT** run `npx tailwindcss init` (does not exist in v4), do **NOT** create tailwind.config.js or postcss.config.js.

- [ ] **Step 2: Configure Vite — React + Tailwind plugins + /api proxy**

```typescript
// frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Backend serves under /api already — no path rewrite needed.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 3: Fonts + title in index.html**

Replace the `<head>` contents of `frontend/index.html` (keep the template's `<body>`):

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500..900;1,9..144,500..900&family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
      rel="stylesheet"
    />
    <title>GetMeASeat — find a confirmed berth</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Tailwind v4 entry CSS with the design tokens**

Replace `frontend/src/index.css` entirely:

```css
@import "tailwindcss";

@theme {
  /* Type: heritage-ticket pairing — Fraunces display serif, Archivo body,
     IBM Plex Mono for train numbers / availability strings. */
  --font-display: "Fraunces", Georgia, serif;
  --font-body: "Archivo", system-ui, sans-serif;
  --font-ticket: "IBM Plex Mono", ui-monospace, monospace;

  /* Warm cream card-stock surfaces */
  --color-paper-50: oklch(0.985 0.01 85);
  --color-paper-100: oklch(0.955 0.018 85);
  --color-paper-200: oklch(0.92 0.026 85);

  /* Deep railway-blue ink */
  --color-rail-200: oklch(0.87 0.03 255);
  --color-rail-500: oklch(0.55 0.1 255);
  --color-rail-700: oklch(0.42 0.08 255);
  --color-rail-900: oklch(0.3 0.07 255);
  --color-rail-950: oklch(0.23 0.05 255);

  /* Signal-lamp accents; -deep variants keep text readable on cream */
  --color-signal-green: oklch(0.62 0.15 150);
  --color-signal-green-deep: oklch(0.45 0.12 150);
  --color-signal-amber: oklch(0.78 0.16 75);
  --color-signal-amber-deep: oklch(0.52 0.12 75);
  --color-signal-red: oklch(0.52 0.19 25);
}
```

- [ ] **Step 5: Placeholder App.tsx proving the pipeline works**

Delete `frontend/src/App.css` and `frontend/src/assets/react.svg`, then replace `frontend/src/App.tsx`:

```tsx
export default function App() {
  return (
    <div className="grid min-h-dvh place-items-center bg-paper-100">
      <h1 className="font-display text-4xl font-black text-rail-950">
        GetMeASeat<span className="text-signal-amber">.</span>
      </h1>
    </div>
  )
}
```

(`frontend/src/main.tsx` stays as the template generated it — it already imports `index.css`.)

- [ ] **Step 6: Verify**

Run: `npm run dev` then open http://localhost:5173
Expected: cream page, centered "GetMeASeat." in the Fraunces serif with an amber dot — proves Tailwind v4, tokens, and fonts all work. Also run `npm run build`; expected: `tsc -b && vite build` succeeds.

- [ ] **Step 7: Commit**

```powershell
git add frontend
git commit -m "chore: scaffold React frontend with Tailwind v4"
```

---

### Task 10: Typed API client

**Files:**
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: Write the client (types mirror backend schemas.py field-for-field)**

```typescript
// frontend/src/api/client.ts
// Types mirror backend/app/schemas.py — keep the two in sync by hand.

export interface StationStop {
  code: string
  name: string
  distance_km: number
}

export interface TrainRoute {
  train_number: string
  train_name: string
  stations: StationStop[]
}

export interface ParsedAvailability {
  raw: string
  status: 'AVAILABLE' | 'RAC' | 'WAITLIST' | 'NOT_BOOKABLE' | 'UNKNOWN'
  quota: string | null
  seats: number | null
  series_wl: number | null
  current_wl: number | null
}

export interface Recommendation {
  rank: number
  book_from: string
  book_to: string
  board_at: string
  alight_at: string
  action: string
  availability: ParsedAvailability
  probability: number
  score: number
  booked_distance_km: number
  extra_km: number
  fare: number
  extra_fare: number
  requires_boarding_change: boolean
  notes: string[]
}

export interface UserLeg {
  source: string
  destination: string
  distance_km: number
  fare: number
  availability: ParsedAvailability | null
}

export interface RecommendationResponse {
  train_number: string
  train_name: string
  journey_date: string
  user_leg: UserLeg
  pairs_evaluated: number
  recommendations: Recommendation[]
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

async function request<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal })
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body: unknown = await res.json()
      if (
        typeof body === 'object' &&
        body !== null &&
        'detail' in body &&
        typeof body.detail === 'string'
      ) {
        detail = body.detail
      }
    } catch {
      // non-JSON error body — keep the default message
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export function getTrainRoute(trainNumber: string, signal?: AbortSignal): Promise<TrainRoute> {
  return request<TrainRoute>(`/api/trains/${encodeURIComponent(trainNumber)}`, signal)
}

export interface SearchQuery {
  trainNumber: string
  source: string
  destination: string
  date: string // YYYY-MM-DD
}

export function findOptimalRoute(
  query: SearchQuery,
  signal?: AbortSignal,
): Promise<RecommendationResponse> {
  const params = new URLSearchParams({
    train_number: query.trainNumber,
    user_source: query.source,
    user_destination: query.destination,
    date: query.date,
  })
  return request<RecommendationResponse>(`/api/find-optimal-route?${params}`, signal)
}
```

- [ ] **Step 2: Verify it compiles**

Run: `npm run build` (from `frontend/`)
Expected: success — the module isn't imported yet, but `tsc -b` type-checks it.

- [ ] **Step 3: Commit**

```powershell
git add frontend/src/api/client.ts
git commit -m "feat: add typed API client"
```

### Task 11: Display components (badge, meter, card, skeleton, error)

**Files:**
- Create: `frontend/src/components/StatusBadge.tsx`
- Create: `frontend/src/components/ProbabilityMeter.tsx`
- Create: `frontend/src/components/RecommendationCard.tsx`
- Create: `frontend/src/components/SkeletonResults.tsx`
- Create: `frontend/src/components/ErrorBanner.tsx`

- [ ] **Step 1: StatusBadge — color-coded raw availability chip**

```tsx
// frontend/src/components/StatusBadge.tsx
import type { ParsedAvailability } from '../api/client'

const STATUS_STYLES: Record<ParsedAvailability['status'], string> = {
  AVAILABLE: 'border-signal-green/50 bg-signal-green/15 text-signal-green-deep',
  RAC: 'border-signal-amber/60 bg-signal-amber/20 text-signal-amber-deep',
  WAITLIST: 'border-signal-amber/60 bg-signal-amber/20 text-signal-amber-deep',
  NOT_BOOKABLE: 'border-signal-red/40 bg-signal-red/10 text-signal-red',
  UNKNOWN: 'border-rail-200 bg-rail-200/40 text-rail-700',
}

interface StatusBadgeProps {
  availability: ParsedAvailability
}

export function StatusBadge({ availability }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-1 font-ticket text-xs font-semibold tracking-wide ${STATUS_STYLES[availability.status]}`}
    >
      {availability.raw}
    </span>
  )
}
```

- [ ] **Step 2: ProbabilityMeter — the one permitted inline style (dynamic width)**

```tsx
// frontend/src/components/ProbabilityMeter.tsx
interface ProbabilityMeterProps {
  probability: number // 0..1
}

export function ProbabilityMeter({ probability }: ProbabilityMeterProps) {
  const pct = Math.round(probability * 100)
  const tone = pct >= 75 ? 'bg-signal-green' : pct >= 40 ? 'bg-signal-amber' : 'bg-signal-red'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-rail-200/60">
        {/* width is data-driven — the only style not expressible as a utility */}
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-ticket text-sm font-medium text-rail-900">{pct}%</span>
    </div>
  )
}
```

- [ ] **Step 3: RecommendationCard — the ticket stub**

```tsx
// frontend/src/components/RecommendationCard.tsx
import type { Recommendation } from '../api/client'
import { ProbabilityMeter } from './ProbabilityMeter'
import { StatusBadge } from './StatusBadge'

interface RecommendationCardProps {
  rec: Recommendation
  highlight?: boolean
}

export function RecommendationCard({ rec, highlight = false }: RecommendationCardProps) {
  return (
    <article
      className={`overflow-hidden rounded-xl border bg-paper-50 shadow-sm transition-shadow hover:shadow-md ${
        highlight ? 'border-signal-amber ring-1 ring-signal-amber/40' : 'border-rail-200'
      }`}
    >
      {/* Stub: perforated edge with punched holes */}
      <div className="relative border-b-2 border-dashed border-rail-200 px-5 pb-4 pt-5">
        <span
          aria-hidden
          className="absolute -bottom-3 -left-3 size-6 rounded-full border border-rail-200 bg-paper-100"
        />
        <span
          aria-hidden
          className="absolute -bottom-3 -right-3 size-6 rounded-full border border-rail-200 bg-paper-100"
        />

        <div className="flex items-center justify-between gap-2">
          <span
            className={`rounded-sm px-2 py-0.5 font-ticket text-[11px] font-bold uppercase tracking-[0.2em] ${
              highlight ? 'bg-signal-amber text-rail-950' : 'bg-rail-200/60 text-rail-700'
            }`}
          >
            {highlight ? '#1 · Best bet' : `#${rec.rank}`}
          </span>
          <StatusBadge availability={rec.availability} />
        </div>

        <p className="mt-3 font-ticket text-3xl font-semibold tracking-tight text-rail-950">
          {rec.book_from}
          <span className="mx-2 text-rail-500">➝</span>
          {rec.book_to}
        </p>
        <p className="mt-1 text-xs text-rail-700">
          board at <span className="font-semibold">{rec.board_at}</span> · alight at{' '}
          <span className="font-semibold">{rec.alight_at}</span>
        </p>
      </div>

      <div className="space-y-4 px-5 pb-5 pt-4">
        <p className="text-sm leading-relaxed text-rail-950">{rec.action}</p>

        <div>
          <p className="mb-1 font-ticket text-[11px] uppercase tracking-[0.18em] text-rail-700">
            Confirmation chance
          </p>
          <ProbabilityMeter probability={rec.probability} />
        </div>

        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div>
            <dt className="sr-only">Fare</dt>
            <dd className="font-ticket font-semibold text-rail-950">₹{rec.fare}</dd>
          </div>
          {rec.extra_fare > 0 && (
            <div>
              <dt className="sr-only">Extra fare</dt>
              <dd className="text-signal-amber-deep">+₹{rec.extra_fare} vs direct</dd>
            </div>
          )}
          {rec.extra_km > 0 && (
            <div>
              <dt className="sr-only">Extra distance</dt>
              <dd className="text-rail-700">+{rec.extra_km} km booked</dd>
            </div>
          )}
        </dl>

        {rec.notes.length > 0 && (
          <ul className="space-y-1.5 border-t border-rail-200/70 pt-3">
            {rec.notes.map((note) => (
              <li key={note} className="flex gap-2 text-xs leading-relaxed text-rail-700">
                <span aria-hidden className="text-signal-amber-deep">
                  ⚠
                </span>
                {note}
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  )
}
```

- [ ] **Step 4: SkeletonResults and ErrorBanner**

```tsx
// frontend/src/components/SkeletonResults.tsx
export function SkeletonResults() {
  return (
    <div className="mt-10 space-y-5" aria-hidden>
      <div className="h-12 animate-pulse rounded-lg bg-rail-200/50" />
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="h-64 animate-pulse rounded-xl bg-rail-200/50 md:col-span-2" />
        <div className="h-64 animate-pulse rounded-xl bg-rail-200/40" />
        <div className="h-64 animate-pulse rounded-xl bg-rail-200/40" />
      </div>
    </div>
  )
}
```

```tsx
// frontend/src/components/ErrorBanner.tsx
interface ErrorBannerProps {
  message: string
}

export function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <p
      role="alert"
      className="mt-10 rounded-lg border border-signal-red/40 bg-signal-red/10 px-4 py-3 text-sm text-signal-red"
    >
      {message}
    </p>
  )
}
```

- [ ] **Step 5: Verify it compiles**

Run: `npm run build`
Expected: success (components not yet wired into App — `tsc -b` still checks them).

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/components
git commit -m "feat: add result display components"
```

### Task 12: SearchForm + ResultsList + App assembly

**Files:**
- Create: `frontend/src/components/SearchForm.tsx`
- Create: `frontend/src/components/ResultsList.tsx`
- Modify: `frontend/src/App.tsx` (replace the Task 9 placeholder)

- [ ] **Step 1: SearchForm — auto-loads the route when 5 digits are typed**

```tsx
// frontend/src/components/SearchForm.tsx
import { useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { getTrainRoute, type SearchQuery, type TrainRoute } from '../api/client'

interface SearchFormProps {
  onSearch: (query: SearchQuery) => void
  searching: boolean
}

const DAY_MS = 86_400_000
const ARP_DAYS = 60 // IRCTC advance reservation period
const toInputDate = (d: Date) => d.toISOString().slice(0, 10)

const LABEL = 'block font-ticket text-[11px] font-medium uppercase tracking-[0.18em] text-rail-700'
const FIELD =
  'mt-1.5 w-full rounded-md border border-rail-200 bg-white px-3 py-2.5 font-ticket text-sm text-rail-950 ' +
  'placeholder:text-rail-500/50 focus:border-rail-500 focus:outline-none focus:ring-2 focus:ring-rail-500/30 ' +
  'disabled:cursor-not-allowed disabled:bg-paper-200/60 disabled:text-rail-700/50'

export function SearchForm({ onSearch, searching }: SearchFormProps) {
  const [route, setRoute] = useState<TrainRoute | null>(null)
  const [routeError, setRouteError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const minDate = toInputDate(new Date())
  const maxDate = toInputDate(new Date(Date.now() + ARP_DAYS * DAY_MS))

  async function handleTrainNumberChange(e: ChangeEvent<HTMLInputElement>) {
    const value = e.target.value.trim()
    setRoute(null)
    setRouteError(null)
    if (!/^\d{5}$/.test(value)) return
    abortRef.current?.abort() // a newer keystroke supersedes any in-flight lookup
    const controller = new AbortController()
    abortRef.current = controller
    try {
      setRoute(await getTrainRoute(value, controller.signal))
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      setRouteError(err instanceof Error ? err.message : 'Could not load this train')
    }
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const data = new FormData(e.currentTarget)
    onSearch({
      trainNumber: String(data.get('trainNumber') ?? ''),
      source: String(data.get('source') ?? ''),
      destination: String(data.get('destination') ?? ''),
      date: String(data.get('date') ?? ''),
    })
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-10 rounded-xl border border-rail-200 bg-paper-50 p-5 shadow-sm sm:p-6"
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label htmlFor="trainNumber" className={LABEL}>
            Train number
          </label>
          <input
            id="trainNumber"
            name="trainNumber"
            type="text"
            inputMode="numeric"
            placeholder="12345"
            required
            pattern="\d{5}"
            maxLength={5}
            onChange={handleTrainNumberChange}
            className={`${FIELD} tracking-[0.3em]`}
          />
          {route && (
            <p className="mt-1.5 text-xs text-signal-green-deep">
              {route.train_name} · {route.stations.length} stops
            </p>
          )}
          {routeError && <p className="mt-1.5 text-xs text-signal-red">{routeError}</p>}
        </div>

        <div>
          <label htmlFor="source" className={LABEL}>
            From
          </label>
          <select id="source" name="source" required disabled={!route} className={FIELD} defaultValue="">
            <option value="" disabled>
              {route ? 'Select station' : 'Enter train first'}
            </option>
            {route?.stations.map((s) => (
              <option key={s.code} value={s.code}>
                {s.code} — {s.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="destination" className={LABEL}>
            To
          </label>
          <select
            id="destination"
            name="destination"
            required
            disabled={!route}
            className={FIELD}
            defaultValue=""
          >
            <option value="" disabled>
              {route ? 'Select station' : 'Enter train first'}
            </option>
            {route?.stations.map((s) => (
              <option key={s.code} value={s.code}>
                {s.code} — {s.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="date" className={LABEL}>
            Journey date
          </label>
          <input
            id="date"
            name="date"
            type="date"
            required
            min={minDate}
            max={maxDate}
            className={FIELD}
          />
        </div>
      </div>

      <button
        type="submit"
        disabled={searching || !route}
        className="mt-5 w-full rounded-md bg-rail-900 px-6 py-3 font-ticket text-sm font-semibold uppercase tracking-[0.2em] text-paper-50 transition-colors hover:bg-rail-700 focus:outline-none focus:ring-2 focus:ring-rail-500 focus:ring-offset-2 focus:ring-offset-paper-50 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
      >
        {searching ? 'Checking combinations…' : 'Find me a seat'}
      </button>
    </form>
  )
}
```

- [ ] **Step 2: ResultsList — user-leg strip + spotlighted card grid**

```tsx
// frontend/src/components/ResultsList.tsx
import type { RecommendationResponse } from '../api/client'
import { RecommendationCard } from './RecommendationCard'
import { StatusBadge } from './StatusBadge'

interface ResultsListProps {
  data: RecommendationResponse
}

export function ResultsList({ data }: ResultsListProps) {
  const { user_leg: leg, recommendations } = data
  return (
    <section className="mt-10" aria-label="Recommendations">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-rail-950 px-4 py-3 text-paper-50">
        <p className="font-ticket text-sm">
          <span className="text-paper-50/60">YOUR LEG · </span>
          {leg.source} ➝ {leg.destination} · {leg.distance_km} km · ₹{leg.fare}
        </p>
        <div className="flex items-center gap-3">
          {leg.availability && <StatusBadge availability={leg.availability} />}
          <p className="font-ticket text-[11px] uppercase tracking-[0.18em] text-paper-50/60">
            {data.pairs_evaluated} combos checked
          </p>
        </div>
      </div>

      {recommendations.length === 0 ? (
        <p className="mt-8 rounded-lg border border-dashed border-rail-200 p-8 text-center text-sm text-rail-700">
          No bookable combination right now — every covering pair came back REGRET or
          unparseable. Try another date.
        </p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-2">
          {recommendations.map((rec) => (
            <div
              key={`${rec.book_from}-${rec.book_to}`}
              className={rec.rank === 1 ? 'md:col-span-2' : ''}
            >
              <RecommendationCard rec={rec} highlight={rec.rank === 1} />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
```

- [ ] **Step 3: App.tsx — layout + the search state machine**

```tsx
// frontend/src/App.tsx
import { useRef, useState } from 'react'
import { ApiError, findOptimalRoute, type RecommendationResponse, type SearchQuery } from './api/client'
import { ErrorBanner } from './components/ErrorBanner'
import { ResultsList } from './components/ResultsList'
import { SearchForm } from './components/SearchForm'
import { SkeletonResults } from './components/SkeletonResults'

type ResultsState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: RecommendationResponse }

export default function App() {
  const [results, setResults] = useState<ResultsState>({ status: 'idle' })
  const abortRef = useRef<AbortController | null>(null)

  async function handleSearch(query: SearchQuery) {
    abortRef.current?.abort() // resubmits cancel the stale request
    const controller = new AbortController()
    abortRef.current = controller
    setResults({ status: 'loading' })
    try {
      const data = await findOptimalRoute(query, controller.signal)
      setResults({ status: 'success', data })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const message =
        err instanceof ApiError
          ? err.message
          : 'Could not reach the server — is the backend running?'
      setResults({ status: 'error', message })
    }
  }

  return (
    <div className="min-h-dvh bg-paper-100 font-body text-rail-950">
      <header className="border-t-4 border-signal-amber bg-rail-950 text-paper-50">
        <div className="mx-auto flex max-w-5xl items-baseline justify-between px-4 py-4 sm:px-6">
          <p className="font-display text-2xl font-bold tracking-tight">
            GetMeASeat<span className="text-signal-amber">.</span>
          </p>
          <p className="hidden font-ticket text-[11px] uppercase tracking-[0.25em] text-paper-50/60 sm:block">
            Alternate-leg berth finder
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 pb-20 pt-10 sm:px-6 sm:pt-14">
        <section className="max-w-2xl">
          <h1 className="font-display text-4xl font-black leading-[1.05] sm:text-5xl lg:text-6xl">
            Waitlisted? <span className="italic text-rail-700">Outsmart the quota.</span>
          </h1>
          <p className="mt-4 text-base leading-relaxed text-rail-700 sm:text-lg">
            The same train hides different quotas on different station pairs. We check every
            booking combination that covers your journey and rank the ones most likely to
            confirm.
          </p>
        </section>

        <SearchForm onSearch={handleSearch} searching={results.status === 'loading'} />

        {results.status === 'loading' && <SkeletonResults />}
        {results.status === 'error' && <ErrorBanner message={results.message} />}
        {results.status === 'success' && <ResultsList data={results.data} />}
      </main>

      <footer className="border-t border-rail-200 py-6">
        <p className="mx-auto max-w-5xl px-4 text-xs text-rail-700/70 sm:px-6">
          Probabilities are heuristics based on public waitlist-clearance patterns, not
          guarantees. Demo data — train 12345, stations A–F.
        </p>
      </footer>
    </div>
  )
}
```

- [ ] **Step 4: Verify the full flow in the browser**

Run backend (`.\.venv\Scripts\fastapi.exe dev app/main.py` from `backend/`) and frontend (`npm run dev` from `frontend/`). Open http://localhost:5173 and: type `12345` → "Demo Express · 6 stops" appears and selects enable; pick C → D, a date within 60 days, submit → skeleton flashes, then the dark "YOUR LEG" strip and up to 3 ticket cards render, rank 1 full-width with the amber Best-bet tag. Type `99999` → red "Train 99999 not found" under the input. Also run `npm run build` — expected: success.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src
git commit -m "feat: assemble search UI"
```

---

### Task 13: README + final verification sweep

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

````markdown
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
````

- [ ] **Step 2: Full verification sweep**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests -q   # expect: all green
cd ..\frontend; npm run build                                # expect: success
```

Then with both dev servers running, check responsiveness in browser devtools at 375 px (form stacks to one column, button full-width, cards single-column), 768 px (two-column form, rank-1 card spans both columns), and 1280 px (four-column form row). Keyboard-tab through the form — focus rings visible on every field.

- [ ] **Step 3: Final commit**

```powershell
git add README.md
git commit -m "docs: add README with run and swap instructions"
```

---

## Future Work (explicitly out of scope now)

- **Real provider:** implement `RailDataProvider` against the IRCTC API/scraper; add `travel_class` as a parameter end-to-end (availability is per class — first thing a real provider needs).
- **Probability model:** replace the heuristic constants with a model trained on historical clearance data; account for festival seasonality.
- **Boarding-point-change automation/reminders** (rules changed to "up to 30 min before departure, CNF/RAC only" from April 2026 — verify the live rule then).
- Frontend component tests (vitest 4 + @testing-library/react 16) if the UI grows beyond one view.

## Post-Review Fixes (applied 2026-06-12, after a 26-agent adversarial review)

The plan above was implemented as written; a multi-dimension review then confirmed 12 findings, all fixed in the `fix:` commit that follows the plan's 13 commits:

1. **Fare model** (`fixtures.py`): whole-distance rebate made longer tickets cheaper at every slab boundary (fare(500)=550 > fare(501)=490). Rewritten as marginal per-slab rates with ceil-to-₹5 rounding — monotone by construction; boundary test added. `calculate_fare(170)` is now 205, not 190.
2. **Parser** (`parser.py`): `AVAILABLE-0000`/`AVL 0` (zero berths) parsed as AVAILABLE at 0.99 probability → now NOT_BOOKABLE.
3. **Parser**: RAC/WL regexes now accept hyphenated forms (`RAC-12`, `GNWL-15/WL-10`) as the docstring promised.
4. **Date validation** (`recommendations.py` + `SearchForm.tsx`): both sides now anchor "today" to Asia/Kolkata (the railway's booking day) instead of server-local vs UTC; `tzdata` added to requirements for Windows.
5. **StatusBadge**: new `tone="dark"` style map + `-bright` color tokens — the user-leg badge on the dark bar was at ~2:1 contrast, now AA.
6. **SearchForm**: route lookup moved into an effect with cleanup-abort (stale responses could repopulate the form after the input was edited to an invalid value); input is controlled; transient failures get a Retry button and friendly copy.
7. **A11y**: route-lookup result/error live region, sr-only search-progress announcer in App, submit button uses `aria-disabled` + submit guard so keyboard focus isn't dropped mid-search.
8. **Contrast tokens**: placeholder `text-rail-700/80`, footer `text-rail-700`.
9. **Test gap**: `test_unbookable_pairs_are_excluded` now guards the capture-before-skip ordering that keeps `user_leg.availability` populated for a REGRET baseline.

Backend suite is now 67 tests, all passing; frontend build + lint clean.

## Self-Review Notes

Checked against the spec: endpoint + 4 user-named params ✓; hardcoded A–F route with distances ✓; `get_seat_status` returning the four example string shapes (plus real-world variants) ✓; covering-pairs-only enumeration ✓; parse → rank with AVAILABLE > GNWL > RLWL > PQWL ✓; same-quota lower-WL-first (strictly monotonic curve) ✓; distance penalty with "significantly better" semantics ✓; top-3 JSON with action strings ✓; modular + commented + edge cases (invalid station, direction, same station, unknown train, malformed/out-of-window date) ✓; React + Tailwind-only styling, responsive ✓; all fake data isolated in `providers/mock/` ✓. Type names cross-checked between schemas.py, client.ts, and every component import.

