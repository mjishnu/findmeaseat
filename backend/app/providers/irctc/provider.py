"""Live RailDataProvider backed by erail.in + confirmtkt (via IRCTCClient).

Thin adapter: it shapes the client's output into the app's schemas and returns
confirmtkt's availability display string UNPARSED — app.core.parser owns
normalization, so one weird upstream string degrades to UNKNOWN rather than
breaking the search.
"""

import datetime as dt

from app.providers.irctc import client as irctc_client
from app.schemas import (
    BookingQuota,
    RawClassOffer,
    RawTrainBetween,
    StationStop,
    TrainRoute,
    TravelClass,
)

# Returned when the train/class is not offered on a segment. The parser maps it
# to NOT_BOOKABLE, so the service simply skips that pair (not an error).
_UNBOOKABLE = "NOT AVAILABLE"


def _offers(cache: dict | None, class_order: list[str]) -> list[RawClassOffer]:
    """One confirmtkt availability cache ({class_code: entry}) -> raw offers,
    ordered by `avlClassesSorted`. Classes our TravelClass enum doesn't model are
    skipped; the richer `availability` string is preferred over the lossy
    `availabilityDisplayName` so the parser keeps the quota prefix (RLWL/GNWL/…)."""
    cache = cache or {}

    def order_key(code: str) -> int:
        try:
            return class_order.index(code)
        except ValueError:
            return len(class_order)

    offers: list[RawClassOffer] = []
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
        offers.append(
            RawClassOffer(
                travel_class=tc,
                raw_availability=raw,
                fare=irctc_client._to_int(entry.get("fare")),
                prediction_pct=irctc_client._to_int(entry.get("predictionPercentage")),
            )
        )
    return offers


def build_raw_trains_between(train_list: list[dict]) -> list[RawTrainBetween]:
    """Shape a confirmtkt trainList into provider-neutral RawTrainBetween rows,
    carrying both General (`availabilityCache`) and Tatkal (`availabilityCacheTatkal`)
    offers as RAW availability strings. Normalization is the service's job."""
    out: list[RawTrainBetween] = []
    for t in train_list:
        order = t.get("avlClassesSorted") or []
        out.append(
            RawTrainBetween(
                train_number=str(t.get("trainNumber") or ""),
                train_name=t.get("trainName") or "",
                from_code=t.get("fromStnCode") or "",
                from_name=t.get("fromStnName") or "",
                to_code=t.get("toStnCode") or "",
                to_name=t.get("toStnName") or "",
                departure_time=t.get("departureTime") or "",
                arrival_time=t.get("arrivalTime") or "",
                duration_min=irctc_client._to_int(t.get("duration")),
                running_days=t.get("runningDays") or "",
                has_pantry=bool(t.get("hasPantry")),
                distance_km=irctc_client._to_int(t.get("distance")),
                general_offers=_offers(t.get("availabilityCache"), order),
                tatkal_offers=_offers(t.get("availabilityCacheTatkal"), order),
                allowed_quotas=t.get("allowedQuotas") or [],
            )
        )
    return out


def build_quota_rows(
    train_list: list[dict],
) -> list[tuple[str, str, str, list["RawClassOffer"]]]:
    """Shape a confirmtkt trainList (fetched with quota=LD|SS) into per-train rows of
    (train_number, from_code, departure_time, offers) read from availabilityCacheForQuota.
    The disambiguators let the frontend map rows back to cards — train_number is not
    unique under enableNearby."""
    out: list[tuple[str, str, str, list[RawClassOffer]]] = []
    for t in train_list:
        order = t.get("avlClassesSorted") or []
        out.append(
            (
                str(t.get("trainNumber") or ""),
                t.get("fromStnCode") or "",
                t.get("departureTime") or "",
                _offers(t.get("availabilityCacheForQuota"), order),
            )
        )
    return out


