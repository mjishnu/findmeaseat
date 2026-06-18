# confirmtkt-Prediction Confirmation Probability — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the class-blind waitlist heuristic with confirmtkt's own per-class `predictionPercentage`, so confirmation chances (and rankings) reflect real per-class/route clearance.

**Architecture:** confirmtkt already returns `predictionPercentage` on every per-class availability entry we fetch. Thread it from the provider into the shared `confirmation_probability`, which now returns `prediction_pct/100` for waitlists (status priors for AVAILABLE/RAC, `None` when no estimate). A new status-tier sort key keeps AVAILABLE/RAC above any waitlist. No new HTTP calls.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, httpx, pytest (asyncio_mode=auto); React 19 + TypeScript + Vite frontend.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-18-confirmation-prediction-design.md` — read it before starting.
- Run backend tests from the `backend/` directory: `python -m pytest` (config: `backend/pytest.ini`, `pythonpath=.`, `asyncio_mode=auto`, `testpaths=tests`).
- **`0` is a real estimate, never `None`.** When reading `predictionPercentage`, use `_to_int(...)` (which maps `None`/unparseable → `None` but keeps `0`). Do NOT append `or None` (that is fare's rule, not prediction's).
- **No silent heuristic fallback.** A missing prediction yields `None` (flagged), never a guessed number.
- Branch already created: `feat/confirmtkt-prediction-ranking` (the spec is committed there).
- Frontend has no test runner; verify the frontend task with `cd frontend && npm run build` (`tsc -b && vite build`).
- Commit messages end with the trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: Schemas — widen probability/score to optional + add `RawClassOffer.prediction_pct`

Additive, backward-compatible change that unblocks every later task. Suite stays green.

**Files:**
- Modify: `backend/app/schemas.py` (`RawClassOffer` ~L97-100; `ClassAvailability.probability` ~L121-126; `Recommendation.probability`/`.score` ~L186-187; `SwitchAlternative.probability` ~L200-205)
- Test: `backend/tests/test_schemas.py`

**Interfaces:**
- Produces: `RawClassOffer.prediction_pct: int | None` (default `None`); `ClassAvailability.probability: float | None`; `Recommendation.probability: float | None`, `Recommendation.score: float | None`; `SwitchAlternative.probability: float | None`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_schemas.py`:

```python
from app.schemas import (
    AvailabilityStatus,
    ClassAvailability,
    ParsedAvailability,
    RawClassOffer,
    TravelClass,
)


def test_raw_class_offer_carries_optional_prediction():
    o = RawClassOffer(travel_class=TravelClass.SL, raw_availability="GNWL5/WL3")
    assert o.prediction_pct is None
    o2 = RawClassOffer(travel_class=TravelClass.SL, raw_availability="GNWL5/WL3", prediction_pct=0)
    assert o2.prediction_pct == 0


def test_class_availability_probability_accepts_none():
    parsed = ParsedAvailability(raw="GNWL5/WL3", status=AvailabilityStatus.WAITLIST)
    ca = ClassAvailability(travel_class=TravelClass.SL, availability=parsed, probability=None)
    assert ca.probability is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_schemas.py::test_raw_class_offer_carries_optional_prediction -v`
Expected: FAIL — `RawClassOffer` has no `prediction_pct` (ValidationError / unexpected keyword).

- [ ] **Step 3: Edit the schemas**

In `backend/app/schemas.py`:

```python
class RawClassOffer(BaseModel):
    travel_class: TravelClass
    raw_availability: str
    fare: int | None = None
    prediction_pct: int | None = None  # confirmtkt predictionPercentage; 0 is real, None = absent
```

```python
class ClassAvailability(BaseModel):
    travel_class: TravelClass
    availability: ParsedAvailability
    probability: float | None  # None when confirmtkt gives no estimate for this leg
    fare: int | None = None  # None when unpriced/unavailable (0 -> None)
```

```python
class Recommendation(BaseModel):
    ...
    probability: float | None  # None when confirmtkt gives no estimate (ranked last, flagged)
    score: float | None        # None mirrors a None probability
    ...
```

```python
class SwitchAlternative(BaseModel):
    ...
    probability: float | None  # always set in practice; widened for consistency
    ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite (no regressions yet — change is additive)**

Run: `python -m pytest -q`
Expected: PASS (existing fields are unchanged; new field defaults to None).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/tests/test_schemas.py
git commit -m "feat(schemas): optional probability/score + RawClassOffer.prediction_pct

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Provider plumbing — expose `predictionPercentage` (no consumers yet)

Adds the prediction-reading method/field across the real provider and both test doubles. Nothing consumes it yet, so the suite stays green.

**Files:**
- Modify: `backend/app/providers/base.py` (add to the `RailDataProvider` Protocol)
- Modify: `backend/app/providers/irctc/provider.py` (`_offers` ~L54-60; add `get_seat_prediction`)
- Modify: `backend/tests/fakes.py` (`FakeRailDataProvider`; its `RawClassOffer` builders ~L174-183, L197-206)
- Modify: `backend/tests/conftest.py` (`StubProvider`)
- Test: `backend/tests/test_irctc_provider.py`, `backend/tests/test_fake_provider.py`

**Interfaces:**
- Consumes: `RawClassOffer.prediction_pct` (Task 1).
- Produces: `provider.get_seat_prediction(train_number, source, destination, journey_date, travel_class, quota=BookingQuota.GENERAL) -> int | None` on `RailDataProvider`, `IRCTCRailDataProvider`, `FakeRailDataProvider`, and `StubProvider`; `StubProvider.__init__` gains `predictions: dict[tuple, int] | None`; `_offers` populates `RawClassOffer.prediction_pct`.

- [ ] **Step 1: Write the failing IRCTC tests**

In `backend/tests/test_irctc_provider.py`, add `predictionPercentage` to the SL/3A entries of `CT_PAYLOAD` (alongside the existing string `"prediction"` key, which the code ignores) — include an explicit `0` and an absent case:

```python
# in CT_PAYLOAD["data"]["trainList"][0]["availabilityCache"]:
#   "SL": {"availabilityDisplayName": "AVAILABLE-0042", "fare": 1245, "prediction": "95%", "predictionPercentage": 95},
#   "3A": {"availabilityDisplayName": "GNWL50/WL30", "fare": 3140, "prediction": "61%", "predictionPercentage": 61},
```

Add a fixture with a `0` and an absent prediction, plus tests:

```python
CT_PAYLOAD_PRED = {
    "data": {
        "trainList": [
            {
                "trainNumber": "12951",
                "avlClassesSorted": ["SL", "3A", "2A"],
                "availabilityCache": {
                    "SL": {"availabilityDisplayName": "GNWL5/WL3", "fare": 700, "predictionPercentage": 88},
                    "3A": {"availabilityDisplayName": "REGRET", "fare": 0, "predictionPercentage": 0},
                    "2A": {"availabilityDisplayName": "GNWL9/WL4", "fare": 1800},  # no prediction key
                },
            }
        ]
    }
}


async def test_get_seat_prediction_reads_percentage():
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_PRED))
    try:
        sl = await provider.get_seat_prediction("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
        ac3 = await provider.get_seat_prediction("12951", "MMCT", "NDLS", DATE, TravelClass.AC3)
        ac2 = await provider.get_seat_prediction("12951", "MMCT", "NDLS", DATE, TravelClass.AC2)
    finally:
        await http.aclose()
    assert sl == 88
    assert ac3 == 0      # a real 0, NOT coerced to None
    assert ac2 is None   # key absent → None


async def test_get_seat_prediction_none_when_train_absent():
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_OTHER))
    try:
        assert await provider.get_seat_prediction("12951", "MMCT", "NDLS", DATE, TravelClass.SL) is None
    finally:
        await http.aclose()


async def test_offers_carry_prediction_pct():
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_PRED))
    try:
        raws = await provider.search_trains_between("MMCT", "NDLS", DATE)
    finally:
        await http.aclose()
    by_class = {o.travel_class.value: o.prediction_pct for o in raws[0].general_offers}
    assert by_class["SL"] == 88
    assert by_class["3A"] == 0
    assert by_class["2A"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_irctc_provider.py::test_get_seat_prediction_reads_percentage -v`
Expected: FAIL — `AttributeError: 'IRCTCRailDataProvider' object has no attribute 'get_seat_prediction'`.

- [ ] **Step 3: Add the Protocol method (`base.py`)**

After `get_seat_status` in the `RailDataProvider` Protocol:

```python
    async def get_seat_prediction(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int | None: ...
    # confirmtkt's predictionPercentage for this cell, read from the SAME cached
    # entry as get_seat_status (no extra request). None when the class/segment has
    # no prediction; a real 0 is preserved (un-bookable rows are filtered earlier
    # via the availability string, so the waitlist path only sees positive values).
```

- [ ] **Step 4: Implement on the IRCTC provider (`irctc/provider.py`)**

Extend `_offers` to populate `prediction_pct` (no `or None` — keep 0):

```python
        offers.append(
            RawClassOffer(
                travel_class=tc,
                raw_availability=raw,
                fare=_to_int(entry.get("fare")),
                prediction_pct=_to_int(entry.get("predictionPercentage")),
            )
        )
```

Add the method (mirrors `get_seat_status`, different key):

```python
    async def get_seat_prediction(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int | None:
        # Same cached confirmtkt response as get_seat_status — no extra request.
        # _to_int keeps a real 0 and maps absent/unparseable -> None.
        train = find_train(
            await self._client.search_segment(source, destination, format_date(journey_date), quota),
            train_number,
        )
        if train is None:
            return None
        return _to_int(class_cache(train, travel_class.value, quota).get("predictionPercentage"))
```

- [ ] **Step 5: Run IRCTC tests**

Run: `python -m pytest tests/test_irctc_provider.py -v`
Expected: PASS.

- [ ] **Step 6: Write the failing fake-provider tests**

In `backend/tests/test_fake_provider.py`:

```python
async def test_get_seat_prediction_is_class_aware_and_deterministic(provider):
    # Find a day where SL and 1A are both waitlisted on the same leg, then assert
    # the AC class is scaled no higher than Sleeper (SL >= 1A) at equal seed.
    found = False
    for day in range(1, 40):
        date = dt.date(2026, 7, day)
        sl_status = await provider.get_seat_status("12345", "A", "D", date, TravelClass.SL)
        ac_status = await provider.get_seat_status("12345", "A", "D", date, TravelClass.AC1)
        if parse_availability(sl_status).status is not AvailabilityStatus.WAITLIST:
            continue
        if parse_availability(ac_status).status is not AvailabilityStatus.WAITLIST:
            continue
        sl_pred = await provider.get_seat_prediction("12345", "A", "D", date, TravelClass.SL)
        ac_pred = await provider.get_seat_prediction("12345", "A", "D", date, TravelClass.AC1)
        if sl_pred is None or ac_pred is None:
            continue
        assert sl_pred >= ac_pred
        # deterministic
        assert sl_pred == await provider.get_seat_prediction("12345", "A", "D", date, TravelClass.SL)
        found = True
        break
    assert found, "no day with both SL and 1A waitlisted + estimated"


async def test_get_seat_prediction_none_for_non_waitlist(provider):
    # AVAILABLE / RAC carry no graded estimate in the fake (priors handle them).
    for day in range(1, 40):
        date = dt.date(2026, 7, day)
        status = await provider.get_seat_status("12345", "A", "F", date, TravelClass.SL)
        if parse_availability(status).status is AvailabilityStatus.AVAILABLE:
            assert await provider.get_seat_prediction("12345", "A", "F", date, TravelClass.SL) is None
            return
    pytest.skip("no AVAILABLE draw in range")


async def test_search_trains_between_offers_carry_prediction(provider):
    raws = await provider.search_trains_between("A", "D", DATE)
    # at least one offer is a waitlist with a numeric prediction, and the field exists on all
    assert all(hasattr(o, "prediction_pct") for o in raws[0].general_offers)
```

- [ ] **Step 7: Run to verify failure**

Run: `python -m pytest tests/test_fake_provider.py::test_get_seat_prediction_is_class_aware_and_deterministic -v`
Expected: FAIL — `AttributeError: ... 'FakeRailDataProvider' object has no attribute 'get_seat_prediction'`.

- [ ] **Step 8: Implement on the fake (`tests/fakes.py`)**

Add a class-scale table and the method to `FakeRailDataProvider`. Seed the base WITHOUT `travel_class` so classes share a base and differ only by scale (guarantees `SL >= 3A >= 2A >= 1A`):

```python
    # Prediction scale per class: AC clears slower than Sleeper at equal waitlist.
    _CLASS_PRED_SCALE = {"SL": 1.0, "2S": 1.0, "3E": 0.85, "3A": 0.82, "CC": 0.8,
                         "2A": 0.68, "FC": 0.6, "EC": 0.6, "1A": 0.5}

    async def get_seat_prediction(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int | None:
        from app.core.parser import parse_availability
        status = await self.get_seat_status(
            train_number, source, destination, journey_date, travel_class, quota
        )
        if parse_availability(status).status is not AvailabilityStatus.WAITLIST:
            return None  # only waitlists carry a graded estimate; priors handle the rest
        # Base is class-INDEPENDENT (no travel_class in the seed) so scaling alone
        # orders the classes; a deterministic slice returns None to exercise that path.
        rng = random.Random(
            f"pred|{train_number}|{source}|{destination}|{journey_date.isoformat()}|{quota.value}"
        )
        if rng.random() < 0.12:
            return None
        base = rng.randint(40, 95)
        scaled = round(base * self._CLASS_PRED_SCALE.get(travel_class.value, 1.0))
        return max(1, scaled)
```

Add `from app.schemas import AvailabilityStatus` to the imports at the top of `tests/fakes.py` (currently absent). Populate `prediction_pct` on the offers built in `search_trains_between` and `search_quota_availability` — add this kwarg to each `RawClassOffer(...)`:

```python
                prediction_pct=await self.get_seat_prediction(
                    route.train_number, source, destination, journey_date, TravelClass(code)
                ),
```

(For `search_quota_availability`, pass `quota` as the final arg to match its loop.)

- [ ] **Step 9: Run the fake-provider tests**

Run: `python -m pytest tests/test_fake_provider.py -v`
Expected: PASS.

- [ ] **Step 10: Add `get_seat_prediction` to `StubProvider` (`tests/conftest.py`)**

Add the `predictions` arg and method (explicit key lookup preserves a `0` value):

```python
    def __init__(
        self,
        statuses: dict[tuple, str],
        class_options: dict[str, int | None] | None = None,
        tatkal_class_options: dict[str, int | None] | None = None,
        predictions: dict[tuple, int] | None = None,
    ):
        self._statuses = statuses
        self._class_options = class_options or {}
        self._tatkal_class_options = tatkal_class_options or {}
        # Keyed like statuses: (src,dst), (src,dst,class), or (src,dst,class,quota).
        self._predictions = predictions or {}
```

```python
    async def get_seat_prediction(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int | None:
        for key in (
            (source, destination, travel_class.value, quota.value),
            (source, destination, travel_class.value),
            (source, destination),
        ):
            if key in self._predictions:
                return self._predictions[key]  # explicit: a real 0 is preserved
        return None
```

- [ ] **Step 11: Run the full suite (still green — nothing consumes prediction yet)**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add backend/app/providers/base.py backend/app/providers/irctc/provider.py \
        backend/tests/fakes.py backend/tests/conftest.py \
        backend/tests/test_irctc_provider.py backend/tests/test_fake_provider.py
git commit -m "feat(provider): expose confirmtkt predictionPercentage (get_seat_prediction + offers)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Ranking + service threading (the coupled core)

`confirmation_probability` is shared by both services, so flipping it and threading the prediction through both consumers (with `None`-guards and the status-tier sort key) is one green unit.

**Files:**
- Modify: `backend/app/core/ranking.py`
- Modify: `backend/app/services/recommendations.py` (`_Candidate` ~L52-63; `_evaluate_pair` ~L259-300; `find_optimal_route` sort ~L104-120; `_build_recommendation` ~L302-349; `_build_alternatives` ~L238-256)
- Modify: `backend/app/services/train_search.py` (`_to_class` ~L90-98)
- Test: `backend/tests/test_ranking.py` (rewrite), `backend/tests/test_recommendation_service.py`, `backend/tests/test_api.py`, `backend/tests/test_train_search_service.py`

**Interfaces:**
- Consumes: `provider.get_seat_prediction` (Task 2); `RawClassOffer.prediction_pct` (Task 1); optional schema fields (Task 1).
- Produces: `confirmation_probability(parsed, prediction_pct: int | None = None) -> float | None`; `option_score(...) -> float | None`; `_Candidate.status_tier: int`.

- [ ] **Step 1: Rewrite `test_ranking.py`**

Replace the whole file:

```python
import pytest

from app.core.ranking import P_AVAILABLE, P_RAC, confirmation_probability, option_score
from app.schemas import AvailabilityStatus as S
from app.schemas import ParsedAvailability, Quota


def _wl(current: int = 5, quota: Quota = Quota.GNWL) -> ParsedAvailability:
    return ParsedAvailability(raw="x", status=S.WAITLIST, quota=quota, current_wl=current)


def _status(status: S, **kw) -> ParsedAvailability:
    return ParsedAvailability(raw="x", status=status, **kw)


def test_waitlist_uses_confirmtkt_prediction():
    assert confirmation_probability(_wl(), prediction_pct=81) == pytest.approx(0.81)
    # A real 0 is a genuine (very low) estimate, NOT "no estimate".
    assert confirmation_probability(_wl(), prediction_pct=0) == 0.0


def test_waitlist_without_prediction_is_none():
    assert confirmation_probability(_wl(), prediction_pct=None) is None
    assert confirmation_probability(_wl()) is None  # default


def test_class_is_no_longer_inferred_from_waitlist_number():
    # Same prediction -> same probability regardless of the WL number (the old
    # WL-curve is gone; confirmtkt's per-class number is the only signal).
    assert confirmation_probability(_wl(3), 70) == confirmation_probability(_wl(40), 70)


def test_available_and_rac_use_status_priors_regardless_of_prediction():
    assert confirmation_probability(_status(S.AVAILABLE, seats=5)) == P_AVAILABLE
    assert confirmation_probability(_status(S.AVAILABLE, seats=5), prediction_pct=10) == P_AVAILABLE
    assert confirmation_probability(_status(S.RAC, current_wl=3)) == P_RAC


def test_unbookable_statuses_score_zero():
    assert confirmation_probability(_status(S.NOT_BOOKABLE)) == 0.0
    assert confirmation_probability(_status(S.UNKNOWN)) == 0.0


def test_option_score_is_none_when_probability_is_none():
    assert option_score(None, extra_fare=0, user_leg_fare=205, extra_km=0, user_leg_km=170) is None


def test_no_penalty_for_exact_leg():
    assert option_score(0.85, extra_fare=0, user_leg_fare=205, extra_km=0, user_leg_km=170) == 0.85


def test_same_fare_is_not_penalized_for_distance():
    assert option_score(0.85, extra_fare=0, user_leg_fare=205, extra_km=190, user_leg_km=170) == 0.85


def test_cost_penalty_grows_concavely():
    base = 0.85
    near = option_score(base, extra_fare=205, user_leg_fare=205, extra_km=0, user_leg_km=170)
    far = option_score(base, extra_fare=820, user_leg_fare=205, extra_km=0, user_leg_km=170)
    assert base > near > far
    assert (base - far) == pytest.approx(2 * (base - near))


def test_distance_proxy_used_when_fare_unknown():
    penalized = option_score(0.85, extra_fare=None, user_leg_fare=None, extra_km=170, user_leg_km=170)
    assert penalized == pytest.approx(0.85 - 0.10)


def test_score_clamped_at_zero():
    assert option_score(0.05, extra_fare=8000, user_leg_fare=100, extra_km=0, user_leg_km=100) == 0.0
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_ranking.py -v`
Expected: FAIL — `confirmation_probability` rejects `prediction_pct`, and `option_score(None, ...)` raises.

- [ ] **Step 3: Rewrite `ranking.py`**

Replace the module body (keep `P_AVAILABLE`, `P_RAC`, `COST_PENALTY_WEIGHT`, `option_score`; delete `_WL_CURVE`, `_wl_probability`, `QUOTA_FACTOR`; drop the now-unused `Quota` import):

```python
"""Confirmation-probability from confirmtkt's per-class prediction + the
distance-penalized score.

The waitlist chance is confirmtkt's own `predictionPercentage` (trained on real
per-class/route/season clearance), not a local heuristic. AVAILABLE and RAC keep
fixed status priors — a seat in hand is a fact, not a prediction. A waitlist with
no upstream estimate returns None (the caller flags it and ranks it last).
"""
import math

from app.schemas import AvailabilityStatus, ParsedAvailability

P_AVAILABLE = 0.99
P_RAC = 0.95  # RAC guarantees travel (shared berth) — better than every waitlist

# Weight of the concave extra-cost penalty in option_score.
COST_PENALTY_WEIGHT = 0.10


def confirmation_probability(
    parsed: ParsedAvailability, prediction_pct: int | None = None
) -> float | None:
    """Probability that booking this status ends in a confirmed (or RAC) berth.

    Returns None for a waitlist with no confirmtkt estimate — distinct from a real
    0.0 estimate. NOT_BOOKABLE/UNKNOWN return 0.0 (only reachable via train-search;
    the seat-finder drops those pairs before ranking)."""
    if parsed.status is AvailabilityStatus.AVAILABLE:
        return P_AVAILABLE
    if parsed.status is AvailabilityStatus.RAC:
        return P_RAC
    if parsed.status is AvailabilityStatus.WAITLIST:
        if prediction_pct is not None:
            return prediction_pct / 100.0  # confirmtkt's estimate (0 stays 0.0)
        return None
    return 0.0


def option_score(
    probability: float | None,
    extra_fare: int | None,
    user_leg_fare: int | None,
    extra_km: int,
    user_leg_km: int,
) -> float | None:
    """Probability minus a concave penalty on the EXTRA COST of a longer booking.

    Returns None when probability is None (a no-estimate option carries no score).
    The penalty tracks the real fare difference, not raw distance: IR fares are
    telescopic, so a longer booking often costs the same and must not be demoted.
    sqrt keeps it concave; falls back to a distance proxy when the fare is unknown.
    """
    if probability is None:
        return None
    if extra_fare is not None and user_leg_fare:
        ratio = extra_fare / user_leg_fare
    elif user_leg_km:
        ratio = extra_km / user_leg_km
    else:
        ratio = 0.0
    if ratio <= 0:
        return probability
    penalty = COST_PENALTY_WEIGHT * math.sqrt(ratio)
    return max(0.0, probability - penalty)
```

- [ ] **Step 4: Run ranking tests**

Run: `python -m pytest tests/test_ranking.py -v`
Expected: PASS. (Full suite is now RED at the service layer — fixed in the next steps.)

- [ ] **Step 5: Thread prediction + status tier into the seat-finder (`recommendations.py`)**

Add the import and a status-tier map near the top:

```python
from app.core.ranking import confirmation_probability, option_score
from app.schemas import AvailabilityStatus
...
# Higher tier always outranks lower, regardless of score — a seat in hand (or RAC's
# guaranteed berth) must never be ranked below a waitlist, even a ~100% one.
_STATUS_TIER = {
    AvailabilityStatus.AVAILABLE: 3,
    AvailabilityStatus.RAC: 2,
    AvailabilityStatus.WAITLIST: 1,
}
```

Add `status_tier` to `_Candidate` and widen its numeric fields:

```python
@dataclass
class _Candidate:
    board: StationStop
    alight: StationStop
    parsed: ParsedAvailability
    status_tier: int
    probability: float | None
    score: float | None
    booked_km: int
    extra_km: int
    fare: int | None
    extra_fare: int | None
```

In `_evaluate_pair`, fetch the prediction (warm cache) and pass it through:

```python
        booked_km = km[alight.code] - km[board.code]
        extra_km = booked_km - user_leg_km
        fare = await self._provider.get_fare(
            train_number, board.code, alight.code, journey_date, travel_class, quota
        )
        prediction = await self._provider.get_seat_prediction(
            train_number, board.code, alight.code, journey_date, travel_class, quota
        )
        extra_fare = (
            fare - user_leg_fare
            if fare is not None and user_leg_fare is not None
            else None
        )
        probability = confirmation_probability(parsed, prediction)
        candidate = _Candidate(
            board=board,
            alight=alight,
            parsed=parsed,
            status_tier=_STATUS_TIER[parsed.status],
            probability=probability,
            score=option_score(probability, extra_fare, user_leg_fare, extra_km, user_leg_km),
            booked_km=booked_km,
            extra_km=extra_km,
            fare=fare,
            extra_fare=extra_fare,
        )
```

(`_evaluate_pair` already returns `candidate=None` for NOT_BOOKABLE/UNKNOWN before this block, so `_STATUS_TIER[parsed.status]` only ever sees the three keys above.)

- [ ] **Step 6: Make the seat-finder sort + baseline None-safe and tier-first (`find_optimal_route`)**

Replace the `candidates.sort(...)` call:

```python
        # Status tier first (Decision 6), then score, raw probability, cost, distance.
        # None score/probability sort last within their tier.
        def _rank_key(c: _Candidate) -> tuple:
            score = c.score if c.score is not None else -math.inf
            prob = c.probability if c.probability is not None else -math.inf
            fare = c.extra_fare if c.extra_fare is not None else math.inf
            return (-c.status_tier, -score, -prob, fare, c.extra_km)

        candidates.sort(key=_rank_key)
```

Make the `chosen_best` baseline None-safe:

```python
        chosen_best = max(
            candidates,
            key=lambda c: c.probability if c.probability is not None else -math.inf,
            default=None,
        )
```

- [ ] **Step 7: Guard the rounds + add the no-estimate note (`_build_recommendation`)**

At the end of `_build_recommendation`, after the existing `notes` logic, add the flag, then guard both rounds:

```python
        if cand.probability is None:
            notes.append(
                "confirmtkt has no confirmation estimate for this leg; ranked last."
            )
        ...
        return Recommendation(
            ...
            probability=round(cand.probability, 3) if cand.probability is not None else None,
            score=round(cand.score, 3) if cand.score is not None else None,
            ...
        )
```

- [ ] **Step 8: Filter no-estimate candidates out of the alternatives ranking (`_build_alternatives`)**

A no-estimate waitlist can't be "strictly better", so drop `None` before the max/compare/sort:

```python
            candidates, _parsed, _skipped, _cell_fare = await self._evaluate_class(
                train_number, pairs, source, destination, km, user_leg_km,
                journey_date, tc, searched_quota,
            )
            candidates = [c for c in candidates if c.probability is not None]
```

(The subsequent `max(...)`, `best.probability <= searched_best_prob`, `round(best.probability, 3)`, and `alternatives.sort(key=lambda a: -a.probability)` are now always over real floats.)

- [ ] **Step 9: Guard the round in train-search (`train_search.py::_to_class`)**

```python
    @staticmethod
    def _to_class(offer: RawClassOffer) -> ClassAvailability:
        parsed = parse_availability(offer.raw_availability)
        p = confirmation_probability(parsed, offer.prediction_pct)
        return ClassAvailability(
            travel_class=offer.travel_class,
            availability=parsed,
            probability=round(p, 3) if p is not None else None,
            fare=offer.fare or None,
        )
```

- [ ] **Step 10: Update the seat-finder service tests (`test_recommendation_service.py`)**

Replace the comment block (L16-19) and `STATUSES`/fixture with prediction-driven inputs, and fix the two ranking assertions that depended on the old heuristic:

```python
# Availability + confirmtkt predictions drive the rank now (no WL-number heuristic).
#   A->F AVAILABLE: status tier 3 -> always first, regardless of cost penalty.
#   A->D GNWL wl10 @ pred 80% -> prob 0.80 (waitlist tier)
#   C->D PQWL wl8  @ pred 30% -> prob 0.30 (waitlist tier, exact leg)
STATUSES = {
    ("C", "D"): "PQWL 10/WL 8",
    ("A", "D"): "GNWL 15/WL 10",
    ("A", "F"): "AVAILABLE 10",
}
PREDICTIONS = {
    ("A", "D"): 80,
    ("C", "D"): 30,
}


@pytest.fixture()
def service() -> RecommendationService:
    return RecommendationService(StubProvider(STATUSES, predictions=PREDICTIONS))
```

In `test_ranks_better_quota_from_earlier_station_first`, keep the leg-order and rank assertions but replace the brittle `scores == sorted(...)` line (no longer true: an AVAILABLE covering pair can have a lower *score* than a high-prediction waitlist yet rank first by tier):

```python
async def test_ranks_better_quota_from_earlier_station_first(service):
    res = await service.find_optimal_route("12345", "C", "D", tomorrow())
    legs = [(r.book_from, r.book_to) for r in res.recommendations]
    assert legs == [("A", "F"), ("A", "D"), ("C", "D")]
    assert [r.rank for r in res.recommendations] == [1, 2, 3]
    # AVAILABLE leads by status tier; among the waitlists, the higher confirmtkt
    # prediction (A->D 0.80) outranks the lower one (C->D 0.30).
    assert res.recommendations[0].availability.status is AvailabilityStatus.AVAILABLE
    wl = [r for r in res.recommendations if r.availability.status is AvailabilityStatus.WAITLIST]
    assert [r.probability for r in wl] == [0.8, 0.3]
```

Update `test_travel_class_is_echoed` to pass predictions too (it constructs its own `StubProvider(STATUSES)`):

```python
    service = RecommendationService(StubProvider(STATUSES, predictions=PREDICTIONS))
```

Add two new tests covering Decision 6 and Decision 3:

```python
async def test_available_outranks_a_near_certain_waitlist():
    # Decision 6: a 100%-predicted waitlist must NOT leapfrog an AVAILABLE seat.
    statuses = {("C", "D"): "AVAILABLE 5", ("A", "D"): "GNWL 2/WL 1"}
    svc = RecommendationService(StubProvider(statuses, predictions={("A", "D"): 100}))
    res = await svc.find_optimal_route("12345", "C", "D", tomorrow())
    top = res.recommendations[0]
    assert (top.book_from, top.book_to) == ("C", "D")
    assert top.availability.status is AvailabilityStatus.AVAILABLE


async def test_waitlist_without_estimate_is_ranked_last_and_flagged():
    # Decision 3: a waitlist with no confirmtkt estimate sorts below estimated ones
    # and carries an explanatory note. (A->D has an estimate; C->D does not.)
    statuses = {("A", "D"): "GNWL 9/WL 4", ("C", "D"): "PQWL 9/WL 4"}
    svc = RecommendationService(StubProvider(statuses, predictions={("A", "D"): 55}))
    res = await svc.find_optimal_route("12345", "C", "D", tomorrow())
    legs = [(r.book_from, r.book_to) for r in res.recommendations]
    assert legs.index(("A", "D")) < legs.index(("C", "D"))
    no_est = next(r for r in res.recommendations if (r.book_from, r.book_to) == ("C", "D"))
    assert no_est.probability is None and no_est.score is None
    assert any("no confirmation estimate" in n.lower() for n in no_est.notes)
```

- [ ] **Step 11: Update the API tests (`test_api.py`)**

Add predictions to the fixture so the documented leg order still holds, and tolerate `null`:

```python
PREDICTIONS = {("A", "D"): 80, ("C", "D"): 30}
...
    app.dependency_overrides[get_provider] = lambda: StubProvider(STATUSES, predictions=PREDICTIONS)
```

The existing `legs == [("A", "F"), ("A", "D"), ("C", "D")]` assertion still holds (AVAILABLE by tier, then 0.80 > 0.30). Add a check that JSON serialises a present probability:

```python
def test_probability_is_serialised(stubbed):
    res = client.get("/api/find-optimal-route", **_search())
    body = res.json()
    ad = next(r for r in body["recommendations"] if (r["book_from"], r["book_to"]) == ("A", "D"))
    assert ad["probability"] == 0.8
```

- [ ] **Step 12: Update the train-search service tests (`test_train_search_service.py`)**

Run them first to see what breaks:

Run: `python -m pytest tests/test_train_search_service.py -v`

For any assertion that compared `ClassAvailability.probability` to the old heuristic, replace with the prediction-based value. The fake now sets `prediction_pct` on offers, so a waitlist class shows `prediction_pct/100` (or `None` for the deterministic no-estimate slice). Update assertions to either (a) read the expected `round(confirmation_probability(parsed, offer.prediction_pct), 3)`, or (b) assert `probability is None or 0.0 <= probability <= 1.0`. Add one explicit case if a fixture-built offer is available:

```python
def test_to_class_maps_prediction_to_probability():
    from app.schemas import RawClassOffer, TravelClass
    from app.services.train_search import TrainSearchService
    wl = RawClassOffer(travel_class=TravelClass.SL, raw_availability="GNWL9/WL4", prediction_pct=72)
    none_wl = RawClassOffer(travel_class=TravelClass.AC3, raw_availability="GNWL9/WL4")
    assert TrainSearchService._to_class(wl).probability == 0.72
    assert TrainSearchService._to_class(none_wl).probability is None  # no estimate -> display "—"
```

- [ ] **Step 13: Run the full backend suite**

Run: `python -m pytest -q`
Expected: PASS. If `test_train_search_api.py` or `test_train_search_extraction.py` assert old-heuristic probabilities, update those assertions the same way (prediction-based value or `None`/range check) and re-run.

- [ ] **Step 14: Commit**

```bash
git add backend/app/core/ranking.py backend/app/services/recommendations.py \
        backend/app/services/train_search.py backend/tests/test_ranking.py \
        backend/tests/test_recommendation_service.py backend/tests/test_api.py \
        backend/tests/test_train_search_service.py backend/tests/test_train_search_api.py \
        backend/tests/test_train_search_extraction.py
git commit -m "feat(ranking): confirmtkt prediction drives confirmation probability

Drop the class-blind WL-curve x quota heuristic; waitlist chance is now
confirmtkt's predictionPercentage (None when absent, flagged + ranked last).
Add a status-tier sort key so AVAILABLE/RAC always outrank any waitlist.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Frontend — render `null` as "No estimate"

`ProbabilityMeter` is the only component that renders the number; the rest pass it through. Widen the client types and handle `null` in the meter.

**Files:**
- Modify: `frontend/src/components/ProbabilityMeter.tsx`
- Modify: `frontend/src/api/client.ts` (L60, L61, L82, L170)
- Modify: `frontend/src/components/RecommendationCard.tsx` (L57 — type-flow only, likely no edit)
- Verify: `cd frontend && npm run build`

**Interfaces:**
- Consumes: backend now sends `probability`/`score` as `number | null`.
- Produces: `ProbabilityMeter` accepts `probability: number | null`.

- [ ] **Step 1: Widen the client types (`frontend/src/api/client.ts`)**

```ts
// Recommendation (L60-61):
  probability: number | null
  score: number | null
// SwitchAlternative (L82):
  probability: number | null
// ClassAvailability (L170):
  probability: number | null
```

- [ ] **Step 2: Handle `null` in `ProbabilityMeter.tsx`**

```tsx
interface ProbabilityMeterProps {
  probability: number | null // 0..1, or null when confirmtkt has no estimate
}

export function ProbabilityMeter({ probability }: ProbabilityMeterProps) {
  if (probability === null) {
    return (
      <div className="flex items-center gap-2">
        <div className="h-1.5 flex-1 rounded-full bg-rail-200/60" />
        <span className="font-ticket text-sm font-medium text-rail-500">No estimate</span>
      </div>
    )
  }
  const pct = Math.round(probability * 100)
  const tone = pct >= 75 ? 'bg-signal-green' : pct >= 40 ? 'bg-signal-amber' : 'bg-signal-red'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-rail-200/60">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-ticket text-sm font-medium text-rail-900">{pct}%</span>
    </div>
  )
}
```

- [ ] **Step 3: Confirm `RecommendationCard.tsx` type-flows**

Open `frontend/src/components/RecommendationCard.tsx` (L57). It forwards `rec.probability` to `<ProbabilityMeter probability={rec.probability} />`. With both widened to `number | null`, no code change is needed — confirm it compiles in the build step.

- [ ] **Step 4: Build (frontend has no unit-test runner)**

Run: `cd frontend && npm run build`
Expected: `tsc -b` passes with no type errors and `vite build` succeeds. If `tsc` flags any other reader of `.probability`/`.score`, it surfaces here — fix by accepting `number | null` at that site.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/components/ProbabilityMeter.tsx \
        frontend/src/components/RecommendationCard.tsx
git commit -m "feat(ui): render a null confirmation estimate as 'No estimate'

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage**

| Spec item | Task |
|---|---|
| Decision 1 — delete `_WL_CURVE`/`_wl_probability`/`QUOTA_FACTOR` | Task 3 Step 3 |
| Decision 2 — AVAILABLE/RAC priors kept | Task 3 Step 3 (ranking) |
| Decision 3 — missing prediction → None, ranked last, flagged | Task 3 Steps 6,7,10 |
| Decision 4 — `0` preserved, never `None` | Task 2 (`_to_int`, Stub explicit key), Task 3 (test) |
| Decision 5 — `get_seat_status` contract unchanged; sibling method | Task 2 |
| Decision 6 — status-tier sort key | Task 3 Steps 5,6,10 |
| Decision 7 — train-search display-only (no reorder/note) | Task 3 Step 9,12 (probability set; no sort/note added) |
| §1 ranking signature + option_score None | Task 3 Steps 1-3 |
| §2 schema widening + prediction_pct | Task 1 |
| §3 provider + IRCTC + fake + conftest StubProvider | Task 2 |
| §4 seat-finder threading/sort/guards/note/alternatives | Task 3 Steps 5-8,10 |
| §5 train-search round guard | Task 3 Step 9 |
| §6 frontend (ProbabilityMeter, client.ts, RecommendationCard) | Task 4 |
| §Testing — ranking/fake/irctc/recommendation/api/train-search | Tasks 1-3 |

**2. Placeholder scan:** No "TBD/TODO". Task 3 Steps 12-13 say "update any assertion that compared to the old heuristic" — this is genuinely data-dependent on the fake's deterministic draws, so the instruction is to run the named test and replace heuristic-derived expected values with the prediction-based value or a `None`/range check; concrete patterns are shown.

**3. Type consistency:** `confirmation_probability(parsed, prediction_pct=None) -> float | None`, `option_score(...) -> float | None`, `get_seat_prediction(... ) -> int | None`, `_Candidate.status_tier: int`, `RawClassOffer.prediction_pct: int | None` are used identically across Tasks 1-4. `_STATUS_TIER` keys match the three statuses that survive `_evaluate_pair`'s NOT_BOOKABLE/UNKNOWN filter.
