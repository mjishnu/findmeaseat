"""Live RailDataProvider backed by erail.in + confirmtkt (via IRCTCClient).

Thin adapter: it shapes the client's output into the app's schemas and normalizes
confirmtkt's availability display strings through app.core.parser + ranking into ClassAvailability.
"""

from app.core.parser import parse_availability
from app.core.ranking import confirmation_probability
from app.providers.irctc.client import _to_int
from app.schemas import (
    ClassAvailability,
    TrainBetween,
    TravelClass,
)


def _offers(cache: dict | None, class_order: list[str]) -> list[ClassAvailability]:
    """One confirmtkt availability cache ({class_code: entry}) -> ClassAvailability offers,
    ordered by `avlClassesSorted`. Classes our TravelClass enum doesn't model are
    skipped; the richer `availability` string is preferred over the lossy
    `availabilityDisplayName` so the parser keeps the quota prefix (RLWL/GNWL/…)."""
    cache = cache or {}

    def order_key(code: str) -> int:
        try:
            return class_order.index(code)
        except ValueError:
            return len(class_order)

    offers: list[ClassAvailability] = []
    for code in sorted(cache.keys(), key=order_key):
        entry = cache.get(code)
        if not isinstance(entry, dict):
            continue
        try:
            tc = TravelClass(code)
        except ValueError:
            continue  # a class our enum doesn't model
        raw = entry.get("availability") or entry.get("availabilityDisplayName") or ""
        raw = (
            raw.strip().rstrip("#").strip()
        )  # drop confirmtkt's "#" marker for clean display
        if not raw:
            continue
        parsed = parse_availability(raw)
        pred_pct = _to_int(entry.get("predictionPercentage"))
        p = confirmation_probability(parsed, pred_pct)
        offers.append(
            ClassAvailability(
                travel_class=tc,
                availability=parsed,
                probability=round(p, 3),
                fare=_to_int(entry.get("fare")),
            )
        )
    return offers


def build_trains_between(train_list: list[dict]) -> list[TrainBetween]:
    """Shape a confirmtkt trainList into normalized TrainBetween rows,
    carrying General (`availabilityCache`), Tatkal (`availabilityCacheTatkal`),
    and Quota (`availabilityCacheForQuota`) parsed availability offers."""
    out: list[TrainBetween] = []
    for t in train_list:
        order = t.get("avlClassesSorted") or []
        out.append(
            TrainBetween(
                train_number=str(t.get("trainNumber") or ""),
                train_name=t.get("trainName") or "",
                from_code=t.get("fromStnCode") or "",
                from_name=t.get("fromStnName") or "",
                to_code=t.get("toStnCode") or "",
                to_name=t.get("toStnName") or "",
                departure_time=t.get("departureTime") or "",
                arrival_time=t.get("arrivalTime") or "",
                duration_min=_to_int(t.get("duration")),
                running_days=t.get("runningDays") or "",
                has_pantry=bool(t.get("hasPantry")),
                distance_km=_to_int(t.get("distance")),
                general=_offers(t.get("availabilityCache"), order),
                tatkal=_offers(t.get("availabilityCacheTatkal"), order),
                classes=_offers(t.get("availabilityCacheForQuota"), order),
                allowed_quotas=t.get("allowedQuotas") or [],
            )
        )
    return out
