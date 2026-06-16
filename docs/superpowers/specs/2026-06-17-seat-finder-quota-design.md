# Seat-finder Quota — Design Spec

**Status:** Design approved; ready for implementation plan (`writing-plans`).
**Scope:** This is **Spec 2 of 2**. It extends the existing **seat-finder**
(`/api/find-optimal-route`) with a **General/Tatkal quota** dimension and a
**unified best-switch banner**. It depends on no code from Spec 1 (Train Search) —
the two are independent — but builds on the same enabling fact (confirmtkt bundles
both quota caches). Implement after Spec 1 ships, or in parallel; the only shared
surface is the IRCTC provider, and the changes don't collide.

> **Supersedes** the "Spec 2 preview" appendix in
> `2026-06-17-train-search-design.md`: that sketch proposed a single
> `quota_alternative` field mirroring `class_alternatives`. This spec instead
> unifies both axes into one `alternatives` list spanning the full (class × quota)
> grid, because it's still free (cached pair responses) and lets the banner suggest
> a *combined* switch like "Tatkal · 3A" — matching the approved "class, quota, or
> both" intent. See Decision 3.

---

## Goal

Let a user search the seat-finder in **General (GN)** or **Tatkal (TQ)** quota, and
proactively surface when a *different* quota and/or class would confirm more
reliably for the same journey — via one **unified best-switch banner** that replaces
today's class-only suggestion banner.

Today the seat-finder is General-only and already suggests better *classes*
(`class_alternatives` → `ClassSuggestionBanner`). This spec generalizes that one-axis
nudge into a two-axis (class × quota) one, and adds an explicit quota control to the
form — symmetric with the existing Class selector.

## Why it's free (the enabling fact)

The seat-finder already fetches one confirmtkt response **per covering pair**
(`IRCTCClient.search_segment`, cached + single-flighted). Each response carries
**both** `availabilityCache` (GN) and `availabilityCacheTatkal` (TQ) for every
class. `RecommendationService._evaluate_class` is explicitly designed to reuse those
cached pair responses for alternative evaluation "without issuing any extra upstream
requests beyond the searched class's." Evaluating the *other quota* reads a different
key from the **same cached response** — so the whole (class × quota) grid costs zero
extra upstream calls, exactly like today's class alternatives.

Tatkal data is only populated within ~1 day of travel (IRCTC's real Tatkal window),
so for distant dates the TQ cells are NOT_BOOKABLE and simply never surface — the
banner won't fire, and a manual Tatkal search shows a clean empty state.

## Decision Log (read before coding)

1. **New `BookingQuota` enum, kept distinct from `Quota`.** `app/schemas.py`
   already has `Quota` (waitlist *types*: GNWL/RLWL/PQWL…). The booking quota is a
   different concept, so add a separate `BookingQuota` enum (`GENERAL="GN"`,
   `TATKAL="TQ"`). Naming them distinctly avoids the easy confusion. Values are the
   codes confirmtkt uses.

2. **`quota` threads through as a defaulted parameter — backwards compatible.**
   `/api/find-optimal-route` gains `quota: BookingQuota = GENERAL`. The service and
   the provider Protocol methods (`get_seat_status`, `get_fare`, `get_class_options`)
   each gain `quota: BookingQuota = BookingQuota.GENERAL`. Defaulting to GENERAL
   means every existing call site and test behaves identically until it opts in.

3. **Unified (class × quota) `alternatives`, not two separate fields.** Replace
   `_build_class_alternatives` with `_build_alternatives`, which loops the grid of
   `(quota, class)` cells — both quotas × every class each quota offers — excluding
   the searched cell, reusing cached pair responses. It keeps only cells whose best
   across covering pairs is **strictly better** than the searched cell's best
   probability, sorts by probability desc, and **caps at the top 3** (the grid can
   be ~16 cells; the banner stays tidy). This subsumes the old class-only list and
   naturally expresses a combined switch. Backend output shape is a single list;
   the frontend banner shows the best.

4. **Reuse the existing probability/ranking model unchanged.** Each cell's
   availability string flows through `parse_availability` → `confirmation_probability`
   (in `core/`), identical to today. No ranking-constant changes. `core/ranking.py`
   is untouched.

5. **`fare 0 → None` for Tatkal "Not Available".** Same hygiene as Spec 1: an
   unbookable Tatkal cell reports `fare: 0`; coerce to `None` so the UI never shows
   "₹0". (Applies in `get_fare`/alternative fare display.)

6. **The banner replaces the class banner; the backend field is renamed.**
   `class_alternatives: list[ClassAlternative]` → `alternatives: list[SwitchAlternative]`
   (each item gains a `quota`). The response also echoes the searched `quota`.
   `client.ts` types mirror the backend by hand (per its existing comment), so the
   rename is done in lockstep on both sides. `ClassSuggestionBanner` →
   `SwitchSuggestionBanner`.

7. **Form gets a General/Tatkal segmented toggle, symmetric with Class.** Controlled
   in `App` like `travelClass`. Selecting Tatkal for a distant date yields no
   recommendations → a tailored empty state ("No bookable options in Tatkal for this
   date — Tatkal opens ~1 day before travel"), distinct from the generic no-results
   state.

8. **Recommendations note the quota when it's Tatkal.** The searched-quota
   recommendations already describe class implicitly; when `quota == TQ`, the action
   line / notes mention "in Tatkal quota" so the user isn't surprised at IRCTC. Minor
   string change in `_build_recommendation`.

## Architecture (changes to existing files)

Layering unchanged: `routers → services → core/providers`.

### Backend

- **`app/schemas.py`**
  - Add `BookingQuota(str, Enum)` = `GENERAL="GN"`, `TATKAL="TQ"`.
  - Rename `ClassAlternative` → `SwitchAlternative`; add `quota: BookingQuota`.
  - `RecommendationResponse`: add `quota: BookingQuota`; rename
    `class_alternatives: list[ClassAlternative]` → `alternatives: list[SwitchAlternative]`.
- **`app/providers/base.py`** — add `quota: BookingQuota = BookingQuota.GENERAL` to
  `get_seat_status`, `get_fare`, `get_class_options`. Update the Protocol docstring.
- **`app/providers/irctc/provider.py`** — `class_cache(train, code, quota)` selects
  `availabilityCacheTatkal` when `quota is TATKAL` else `availabilityCache`;
  `get_seat_status` / `get_fare` / `get_class_options` pass `quota` through. (Helper
  `class_cache` lives in `irctc/client.py` — update its signature there.)
- **`app/services/recommendations.py`**
  - `find_optimal_route(..., quota=BookingQuota.GENERAL)`; thread `quota` into
    `_evaluate_class` → `_evaluate_pair` (which call the provider).
  - Replace `_build_class_alternatives` with `_build_alternatives(... searched_class,
    searched_quota, searched_best_prob, searched_best_fare)`: iterate
    `for q in (GENERAL, TATKAL): for code in get_class_options(q): skip the searched
    cell; evaluate via the cached pair responses; keep strictly-better; build
    SwitchAlternative(quota=q, ...)`. Sort by probability desc, cap 3.
  - `_build_recommendation`: when `quota is TATKAL`, add the quota mention.
  - Echo `quota` in the response.
- **`app/routers/routes.py`** — add the `quota: BookingQuota = BookingQuota.GENERAL`
  query param to `find_optimal_route` and pass it to the service.

### Frontend (Tailwind heritage-ticket system; reuse `StatusBadge`)

- **`api/client.ts`** — add `BookingQuota = 'GN' | 'TQ'`, a `QUOTAS` label const,
  `DEFAULT_QUOTA = 'GN'`; add `quota` to `SearchQuery` and to `findOptimalRoute`'s
  params; rename `ClassAlternative` → `SwitchAlternative` (+ `quota`); rename
  `RecommendationResponse.class_alternatives` → `alternatives`; add `quota` to
  `RecommendationResponse`.
- **`App.tsx`** — hold `quota` state (default `'GN'`); pass to `SearchForm` and into
  `findOptimalRoute`; render `SwitchSuggestionBanner` from `data.alternatives`, whose
  `onSwitch(nextClass, nextQuota)` sets both `travelClass` and `quota` then
  re-searches. Tatkal-empty results → the tailored empty state.
- **`SearchForm.tsx`** — add a **General/Tatkal** segmented toggle (controlled via
  `quota`/`onQuotaChange` props), placed with the Class selector. (This composes with
  Spec 1's deep-link, which seeds train/from/to/date and leaves quota at its default.)
- **`components/ClassSuggestionBanner.tsx` → `SwitchSuggestionBanner.tsx`** — chips
  show class **and** quota (e.g. `TQ · 3A`), `onSwitch(travel_class, quota)`; header
  generalized to "Better odds in another class or quota". Same green styling and
  `StatusBadge` usage.

## Contracts (schema diff)

```python
class BookingQuota(str, Enum):
    GENERAL = "GN"
    TATKAL = "TQ"

# was ClassAlternative
class SwitchAlternative(BaseModel):
    travel_class: TravelClass
    quota: BookingQuota                 # NEW
    availability: ParsedAvailability
    probability: float
    fare: int | None = None
    fare_delta: int | None = None       # vs the searched (class, quota) direct-leg fare

class RecommendationResponse(BaseModel):
    train_number: str
    train_name: str
    journey_date: dt.date
    travel_class: TravelClass
    quota: BookingQuota                  # NEW (echoes the searched quota)
    user_leg: UserLeg
    pairs_evaluated: int
    pairs_skipped: int = 0
    recommendations: list[Recommendation]
    alternatives: list[SwitchAlternative] = []   # RENAMED from class_alternatives, now spans quota
```

**Endpoint:** `GET /api/find-optimal-route?...&quota=GN|TQ` (default `GN`). Unknown
quota → 422 (enum-validated, like `travel_class`). All other params unchanged.

## Error handling

- Unchanged hierarchy. Invalid quota is a 422 via enum validation. Distant-date
  Tatkal isn't an error — it's an empty recommendation set (200) rendered as the
  tailored empty state. Upstream failure still degrades per pair (`pairs_skipped`)
  and raises `ProviderUnavailableError` → 503 only on total failure.

## Testing (TDD, backend; manual frontend)

- **Provider:** `class_cache` / `get_seat_status` / `get_fare` / `get_class_options`
  read the Tatkal cache when `quota=TATKAL` and the general cache otherwise; default
  stays GENERAL. Extend `backend/tests/fakes.py` with quota-aware canned data (a TQ
  cache that differs from GN, plus a distant-date-empty case).
- **Service:** `quota` threads end-to-end; `_build_alternatives` surfaces
  cross-axis cells (e.g. searched GN·SL → suggests TQ·3A), only strictly-better,
  capped at 3, sorted; Tatkal-empty → no TQ alternatives; **regression:** default GN
  output is byte-identical to today except the new `quota` echo and the field rename.
- **API (`TestClient`):** `?quota=TQ` happy path; default GN; `?quota=ZZ` → 422;
  `alternatives` shape includes `quota`.
- Frontend verified via dev servers (no vitest at this size) — manual checklist in
  the plan, including the toggle, the unified banner switching both axes, and the
  Tatkal-distant empty state.

## Out of scope (YAGNI)

Ladies/Senior and other non-bundled quotas (extra per-class upstream calls);
per-quota fare breakdowns; a quota dimension on the Train Search deep-link (it stays
GN-default — a trivial later extension); changes to ranking constants.

## Backwards-compatibility checklist

- Backend `quota` defaults to `GENERAL` → existing API consumers unaffected.
- The **only** breaking response change is `class_alternatives` → `alternatives`
  (with each item gaining `quota`) and the added `quota` echo. The frontend is the
  sole consumer and is updated in the same change. Update `client.ts`,
  `App.tsx`, the renamed banner, and any test/snapshot referencing
  `class_alternatives`.
