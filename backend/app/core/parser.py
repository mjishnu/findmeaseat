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
_RAC_RE = re.compile(r"^RAC[-\s]*0*(\d+)(?:\s*/\s*RAC[-\s]*0*(\d+))?$")
_WL_RE = re.compile(r"^(GNWL|RLWL|RSWL|PQWL|TQWL|RQWL)[-\s]*0*(\d+)\s*/\s*WL[-\s]*0*(\d+)$")
_BARE_WL_RE = re.compile(r"^WL[-\s]*0*(\d+)$")


def parse_availability(raw: str) -> ParsedAvailability:
    text = re.sub(r"\s+", " ", raw.strip().upper())

    for token in _NOT_BOOKABLE_TOKENS:
        if token in text:
            return ParsedAvailability(raw=raw, status=AvailabilityStatus.NOT_BOOKABLE)

    if m := _AVAILABLE_RE.match(text):
        seats = int(m.group(1)) if m.group(1) else None
        if seats == 0:
            # IRCTC emits "AVAILABLE-0000" when the quota exists but has no
            # berths left — bookable in name only; never recommend it.
            return ParsedAvailability(raw=raw, status=AvailabilityStatus.NOT_BOOKABLE)
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
