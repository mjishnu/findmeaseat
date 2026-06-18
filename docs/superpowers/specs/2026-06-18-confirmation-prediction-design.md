# Confirmation Probability — confirmtkt Prediction Design Spec

**Status:** Design approved; ready for implementation plan (`writing-plans`).
**Scope:** Replace the hand-rolled waitlist confirmation heuristic with confirmtkt's
own per-class `predictionPercentage`. Affects the shared ranking function, so it
improves **both** the seat-finder recommendations and the train-search results list.

> This spec was adversarially verified on 2026-06-18 against the real codebase and a
> live confirmtkt probe (4-agent review). The findings are folded in below —
> notably the empirical Decision 4 reframe, the new status-tier sort key
> (Decision 6), the display-only train-search rule (Decision 7), and the
> `None`-guarding / test-coverage details.

---

## Goal

Make the confirmation-probability number accurate. Today a waitlisted option's
chance is computed purely from its waitlist number and quota type — it is
**class-blind**, so AC 3-tier (3A) at WL10 and Sleeper (SL) at WL10 score
identically. In reality they clear at very different rates (SL has the most berths
and the highest cancellation churn; AC classes far less), so the current ranking
routinely orders options backwards.

Use confirmtkt's per-class `predictionPercentage` instead — an ML estimate trained
on real per-route, per-class, per-season clearance history that already captures
all of this.

## Why it's cheap (the key enabling fact)

The live provider's `IRCTCClient.search_segment(...)` already calls confirmtkt's
`/api/v1/trains/search` (with `showPredictionGlobal=true`) and the response we
already parse carries, **on every per-class availability entry**, a confirmation
prediction we currently discard:

```jsonc
// one entry of availabilityCache / availabilityCacheTatkal / availabilityCacheForQuota
{
  "availability": "RLWL45/WL24",
  "availabilityDisplayName": "WL 24",
  "fare": "1670",
  "prediction": "81% Chance",
  "predictionPercentage": 81,        // <-- the signal we will use
  "confirmTktStatus": "Confirm",     // coarse, out of scope
  "availabilityId": "12904-NZM-BDTS-3A-GN"   // prediction is per source→dest pair
}
```

So the fix needs **no new API key and no new HTTP call** — the prediction is in the
same cached entry as the `availabilityDisplayName` string `get_seat_status` already
reads, and in the same `RawClassOffer`-feeding cache the train list already reads.

**Verified by live probe on 2026-06-18** against NDLS→BCT, HWH→NDLS, CSMT→NDLS
(231 class entries across General + Tatkal). The probe confirmed the current
heuristic ranks real cases backwards:

| Train | Option A | Option B | Current algo picks | confirmtkt reality |
|---|---|---|---|---|
| 12381 Poorva | SL `WL45` | 2A `WL25` | 2A (lower WL) | SL **75%** > 2A **56%** |
| 12618 Mangala | SL `WL20` | 3E `WL7` | 3E (lower WL) | SL **66%** > 3E **62%** |
| 12259 Duronto | 2A `WL15` | 3A `WL28` | 2A (lower WL) | 3A **91%** > 2A **78%** |

The probe also established the field's real-world behavior (drives Decision 4):

- `predictionPercentage` was **present and numeric on 100% of entries** — never
  `null`, never missing.
- **AVAILABLE and RAC entries report `100`** (confirmtkt flattens "you'll travel"
  to 100; we override with our own priors — see Decision 2).
- Bookable **WAITLIST** entries report the real graded odds (observed 50–94 in
  General, 33–35 in Tatkal).
- **`0` is the un-bookable sentinel**: every `REGRET` / `NOT AVAILABLE` row carries
  `predictionPercentage: 0` with `prediction: "No More Booking"`. These rows are
  already mapped to `NOT_BOOKABLE` by the parser **from the availability string**,
  so they never reach the WAITLIST branch of the ranking.
- `availabilityCacheTatkal` entries also carry `predictionPercentage`; the Tatkal
  cache is empty for distant dates and populated ~1 day out, mirroring IRCTC.
- `availabilityId` is keyed per `{trainNo}-{boardStn}-{deboardStn}-{class}-{quota}`,
  so each covering pair gets its own prediction — the seat-finder's core trick (a
  different boarding segment can show a higher chance than the direct leg) still
  works.

## Decision Log (read before coding)

1. **Pure confirmtkt; drop the heuristic.** When `predictionPercentage` is present,
   it *is* the probability. There is no blend with a local model. The
   `_WL_CURVE`, `_wl_probability`, and `QUOTA_FACTOR` machinery is **deleted**.
   (Verified: those three symbols are private to `ranking.py`, no external
   imports / `__all__` / test references, so deletion is safe.)

2. **AVAILABLE / RAC keep fixed status priors, not confirmtkt's %.** `P_AVAILABLE`
   (0.99) and `P_RAC` (0.95) stay. A seat available *now* is a fact, not a
   prediction; it must never be ranked below a waitlist. (User-approved.) The
   ordering guarantee this implies is enforced structurally by Decision 6, because
   a WL prediction can reach 1.00 (> 0.95) and would otherwise outrank RAC.

3. **Missing prediction → keep, rank last, flag (seat-finder only).** When a
   *waitlisted* option has no confirmtkt estimate, we do not guess. Its probability
   is `None`; in the seat-finder it sorts below every option that has a real
   estimate and carries an explanatory note. Nothing is hidden. (User-approved.)
   For the train-search list, `None` is display-only — see Decision 7.

4. **The field is effectively always present; `None` is a robustness fallback.**
   The live probe never saw a `null`/missing `predictionPercentage`. So in practice
   the `None` path fires only when (a) the class/segment is not offered at all, or
   (b) confirmtkt changes/removes the field upstream — i.e. it is a defensive
   fallback, plus a path the fake provider exercises deliberately. **A real `0`
   stays `0.0`** (a genuine very-low estimate), never coerced to `None` — unlike
   fare, where `0 → None`. The un-bookable `0`-rows (`REGRET`/`NOT AVAILABLE`) are
   filtered upstream by the parser as `NOT_BOOKABLE`, so the WAITLIST branch only
   ever sees a positive estimate in practice; the explicit `0 → 0.0` rule is kept
   for correctness and is covered by a dedicated test.

5. **`get_seat_status` keeps its string contract.** The prediction is exposed via a
   new sibling provider method (`get_seat_prediction`, full signature in §3) rather
   than by changing `get_seat_status`'s return type, to keep the seam small and the
   documented contract stable.

6. **Status-tier primary sort key (seat-finder).** The seat-finder sort leads with a
   status tier — `AVAILABLE (3) > RAC (2) > WAITLIST (1)` — *before* score and
   probability. This preserves the pre-existing invariant that AVAILABLE and RAC
   always outrank any waitlist (the old heuristic gave this for free, since its WL
   max was 0.90 < `P_RAC` 0.95; with confirmtkt a WL can now be 1.00 and would
   otherwise leapfrog RAC). Within a tier, ranking is by score, then raw
   probability, then cost, then distance, with `None` last.

7. **Train-search is display-only for the prediction.** The train-search results
   list shows confirmtkt's per-class % as `ClassAvailability.probability`; a `None`
   renders as "—" ("No estimate"). Train-search keeps confirmtkt's existing class
   order (`avlClassesSorted`) — it does **not** reorder classes by probability — and
   adds **no** explanatory note (the note in Decision 3 is seat-finder-only). The
   "ranked last / flagged" behavior of Decision 3 applies to the seat-finder only.

## Architecture & data flow

The prediction is threaded from the provider to the ranking function along the two
existing paths. No new upstream requests.

```
confirmtkt entry ──(predictionPercentage)──┐
                                            │
 seat-finder:  provider.get_seat_prediction(...) ─┐
                                                   ├─► confirmation_probability(parsed, prediction_pct) ─► score/sort
 train list:   RawClassOffer.prediction_pct ───────┘
```

### 1. Ranking — `backend/app/core/ranking.py`

New signature (probability becomes optional):

```python
def confirmation_probability(
    parsed: ParsedAvailability, prediction_pct: int | None = None
) -> float | None:
    if parsed.status is AvailabilityStatus.AVAILABLE:
        return P_AVAILABLE                     # 0.99 — seats in hand, top tier
    if parsed.status is AvailabilityStatus.RAC:
        return P_RAC                           # 0.95 — guaranteed travel
    if parsed.status is AvailabilityStatus.WAITLIST:
        if prediction_pct is not None:
            return prediction_pct / 100.0      # confirmtkt's estimate (0 stays 0.0)
        return None                            # no estimate → ranked last, flagged
    return 0.0                                 # NOT_BOOKABLE / UNKNOWN
```

- **Deleted:** `_WL_CURVE`, `_wl_probability`, `QUOTA_FACTOR`.
- **Kept:** `P_AVAILABLE`, `P_RAC`, `COST_PENALTY_WEIGHT`, `option_score`.
- `option_score(probability, ...)` must accept `probability is None` and return
  `None` (a no-estimate option carries no score). The module docstring is rewritten
  to describe the confirmtkt-prediction source.
- The `0.0` (NOT_BOOKABLE / UNKNOWN) branch is only reachable via the **train-search**
  path; the **seat-finder** excludes those pairs as candidates before ranking
  (`recommendations._evaluate_pair` returns `candidate=None` for NOT_BOOKABLE/UNKNOWN),
  so `0.0` never competes in the seat-finder sort.

### 2. Schemas — `backend/app/schemas.py`

- `RawClassOffer` gains `prediction_pct: int | None = None` (additive, default-None;
  verified safe at every construction/read site).
- `Recommendation.probability`: `float` → `float | None`.
- `Recommendation.score`: `float` → `float | None` (mirrors probability).
- `ClassAvailability.probability`: `float` → `float | None`.
- `SwitchAlternative.probability`: `float` → `float | None` (a strictly-better
  alternative always has a real estimate, so `None` is structurally unreachable
  here — the type widens only for consistency; see Testing).

### 3. Provider — `base.py` + `irctc/provider.py` + `tests/fakes.py` + `tests/conftest.py`

- **Protocol** (`base.py`): add the method, with its full signature (identical to
  `get_seat_status`):
  ```python
  async def get_seat_prediction(
      self, train_number: str, source: str, destination: str,
      journey_date: dt.date, travel_class: TravelClass,
      quota: BookingQuota = BookingQuota.GENERAL,
  ) -> int | None: ...
  ```
  Document that it reads `predictionPercentage` from the **same cached entry** as
  `get_seat_status` (so it costs no extra request) and returns `None` when the
  class/segment carries no prediction.
- **IRCTC provider**: implement `get_seat_prediction` (`find_train` → `class_cache`
  → `predictionPercentage`, coerced to int, `None` when the key is absent — **`0`
  preserved, not coerced to None**). Extend `_offers()` to read
  `predictionPercentage` into each `RawClassOffer.prediction_pct` (same `0`-preserving
  coercion).
- **Fake provider** (`tests/fakes.py`): implement `get_seat_prediction`
  deterministically and **class-aware** (derive a base chance from the rng seed,
  then scale down for AC classes so `SL ≥ 3A ≥ 2A ≥ 1A` at equal seed/WL — letting a
  test assert the class ordering the old heuristic got wrong). Return `None` for a
  small, deterministic subset of waitlisted cells to exercise the flag-and-rank-last
  path. Populate `prediction_pct` on the `RawClassOffer`s built in
  `search_trains_between` / `search_quota_availability`.
- **StubProvider** (`tests/conftest.py`) — **required, or every seat-finder test
  raises `AttributeError`**: `StubProvider` (used by `test_api.py` and the
  `test_recommendation_service.py` fixture, and inherited by `_FlakyProvider`,
  `_EqualFareProvider`, `_NoFareProvider`) implements `get_seat_status` but not the
  new method. Add a `predictions: dict[tuple, int]` constructor arg (same
  most-specific-key resolution as `statuses`) and a `get_seat_prediction` that looks
  it up, returning `None` when unset. Rewritten ranking tests script predictions per
  pair to drive the order.

### 4. Seat-finder service — `backend/app/services/recommendations.py`

- `_evaluate_pair` calls `provider.get_seat_prediction(...)` alongside the existing
  `get_seat_status` (warm cache, no extra HTTP) and passes the result into
  `confirmation_probability(parsed, prediction_pct)`.
- `_Candidate` gains a `status_tier: int` (AVAILABLE=3, RAC=2, WAITLIST=1) and its
  `probability` / `score` become `float | None`.
- **`find_optimal_route` sort** — primary key is `-status_tier` (Decision 6), then
  `-score`, then `-probability`, then `extra_fare`, then `extra_km`. `None` score
  and `None` probability must sort **last within their tier** (coerce `None` to
  `-inf` in the key). Resulting order: AVAILABLE → RAC → WL-with-estimate (by score,
  then raw probability, then cost, then distance) → WL-without-estimate (None,
  flagged, last). NOT_BOOKABLE/UNKNOWN are not candidates at all.
- `chosen_best` baseline: the `max(...)` key (current line ~119) must coerce `None`
  to `-inf` so it does not `TypeError` and so a no-estimate leg never becomes the
  baseline.
- `_build_recommendation`: guard both `round(...)` calls —
  `round(cand.probability, 3) if cand.probability is not None else None` (same for
  `score`). When `cand.probability is None`, append a note:
  *"confirmtkt has no confirmation estimate for this leg; ranked last."*
- `_build_alternatives`: a no-estimate WL cannot be "strictly better", so **filter
  out `None`-probability candidates** before the `max(...)` / `<=` comparison /
  `sort` / `round` (current lines ~238–256). This both honors Decision 3 and avoids
  the `None`-vs-float `TypeError`.

### 5. Train-search service — `backend/app/services/train_search.py`

- `_to_class(offer)` computes `p = confirmation_probability(parsed, offer.prediction_pct)`
  and stores `round(p, 3) if p is not None else None` on
  `ClassAvailability.probability` (guard the existing `round(...)` at line ~96).
- Per Decision 7, **no sort change** and **no note** here — train-search keeps
  confirmtkt's class order and treats `None` as a display-only "—".

### 6. Frontend

The only component that actually renders the number is `ProbabilityMeter.tsx`; the
others either forward it or never read it. The client types live in
`frontend/src/api/client.ts` (not `lib/`).

- **`frontend/src/components/ProbabilityMeter.tsx`** — *primary change.* Widen the
  prop to `probability: number | null`. When `null`, render a neutral "No estimate"
  / em-dash state instead of the meter — today `Math.round(null * 100)` yields `0`,
  so a `null` would otherwise draw a misleading red bar at "0%". Update the `// 0..1`
  prop comment.
- **`frontend/src/api/client.ts`** — widen four declarations to `number | null`:
  `Recommendation.probability` (L60), `Recommendation.score` (L61),
  `SwitchAlternative.probability` (L82), `ClassAvailability.probability` (L170).
- **`frontend/src/components/RecommendationCard.tsx`** — type-flow only: it forwards
  `rec.probability` (now `number | null`) to `ProbabilityMeter` (L57). No display
  logic here; the null handling lives in `ProbabilityMeter`.
- **No edit needed** (verified they never read `.probability` / `.score`):
  `ResultsList.tsx`, `TrainBetweenCard.tsx`, `SeatFinderPanel.tsx`,
  `SwitchSuggestionBanner.tsx`. They pass the data through; the widened types flow
  without rendering changes. (`TrainBetweenCard`'s `ClassChip` shows only
  class/fare/status; it does not display probability today, consistent with
  Decision 7's display-only, no-note rule.)

Probabilities now come straight from confirmtkt; optionally relabel the UI to credit
"confirmtkt chance" — out of scope for this spec.

## Testing

- **`test_ranking.py`** — rewritten:
  - WAITLIST + prediction → `pct / 100` (incl. `0 → 0.0`).
  - WAITLIST + no prediction → `None`.
  - AVAILABLE → `0.99`, RAC → `0.95` regardless of prediction.
  - `option_score(None, ...) is None`.
  - Tests asserting the deleted `_WL_CURVE` / `QUOTA_FACTOR` behavior are removed.
- **`test_fake_provider.py`** — assert `get_seat_prediction` is deterministic,
  class-aware (`SL ≥ 3A ≥ 2A ≥ 1A` at equal seed/WL), and that some cells return
  `None`; assert `RawClassOffer.prediction_pct` is populated.
- **`test_irctc_provider.py`** — its CT payload fixtures currently use the wrong key
  `"prediction"` (string); add `predictionPercentage` (int) **including a `0` and an
  absent case**, then assert `get_seat_prediction` returns the int / `0` / `None`
  and that `_offers` populates `RawClassOffer.prediction_pct`.
- **`test_recommendation_service.py`** (+ `conftest.StubProvider` predictions): a
  covering pair with a higher prediction outranks a lower-WL pair with a lower
  prediction; a no-estimate waitlist option sorts last and gets the explanatory
  note; `probability` / `score` may be `None`; an **AVAILABLE (0.99) outranks a
  WAITLIST with `predictionPercentage=100` (1.00)** — proving the Decision 6 tier
  guarantee; a NOT_BOOKABLE pair is excluded from candidates.
- **`test_api.py`** — response JSON tolerates `probability: null` and `score: null`;
  ranking order reflects predictions and the status tier.
- **`test_train_search_service.py` / `test_train_search_api.py`** — `_to_class` maps
  `offer.prediction_pct` → `probability` including `None`; the round is guarded;
  per Decision 7 a `None`-prediction class keeps its confirmtkt order and is
  display-only (no note, no reorder).
- **SwitchAlternative `None`** — note that it is structurally unreachable (a
  strictly-better alternative always has a real estimate); no test asserts a
  `None` there, or one asserts the structural guarantee.
- **Unaffected:** `test_parser.py`, `test_pairs.py`, `test_stations.py`
  (prediction is structured data, never parsed from the availability string).

## Out of scope

- `confirmTktStatus` (coarse Confirm/Regret verdict — redundant with the %).
- `ticketOpenWindowChances` (train-level signal, mostly `null` in the probe).
- confirmtkt's "Travel Guarantee" (`enableTG` / `tGPlan`).
- Relabelling the UI to attribute the number to confirmtkt; reordering the
  train-search class list by probability.

## Risk / mitigation

- **Upstream changes the field name or stops sending it.** Then prediction is
  `None` everywhere and every waitlist option is flagged "no estimate" (seat-finder)
  / shown as "—" (train-search) — degraded but not wrong, and visibly so. We
  deliberately do **not** silently fall back to the old heuristic (Decision 1).
- **A `0` prediction misread as "no estimate"** would wrongly hide a real low
  chance — guarded explicitly by Decision 4 and a dedicated test.
- **A near-100% waitlist leapfrogging RAC/AVAILABLE** — prevented by the
  status-tier sort key (Decision 6) and asserted by a test.
