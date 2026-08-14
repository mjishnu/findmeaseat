"""Centralized parsing utilities for IRCTC / confirmtkt response payloads.

Covers:
- Availability-string normalisation (IRCTC native & aggregator formats)
- JSON payload extraction (confirmtkt envelope → data dict)
- Live-verify response parsing (availability + fare + prediction)

Unrecognized input degrades gracefully rather than raising.
"""

import json
import re

from app.schemas import AvailabilityStatus, ParsedAvailability

_NOT_BOOKABLE_TOKENS = (
    "REGRET",
    "NOT AVAILABLE",
    "TRAIN DEPARTED",
    "TRAIN CANCELLED",
    "CHARTING DONE",
)
_AVAILABLE_RE = re.compile(r"^(?:AVAILABLE|AVBL|AVL)(?:[-\s]*0*(\d+))?$")
_CURR_AVL_RE = re.compile(r"^CURR_AV(?:B?L)(?:[-\s]*0*(\d+))?$")
_HYBRID_AVAILABLE_RE = re.compile(r"/\s*(?:AVAILABLE|AVBL|AVL)$")
_RAC_RE = re.compile(r"^RAC[-\s]*0*(\d+)(?:\s*/\s*RAC[-\s]*0*(\d+))?$")
_WL_RE = re.compile(r"^[A-Z]+WL[-\s]*0*(?:\d+)\s*/\s*WL[-\s]*0*(\d+)$")
_WL_RAC_RE = re.compile(r"^[A-Z]+WL[-\s]*0*(?:\d+)\s*/\s*RAC[-\s]*0*(\d+)$")
_BARE_WL_RE = re.compile(r"^WL[-\s]*0*(\d+)$")


def parse_availability(raw: str) -> ParsedAvailability:
    # confirmtkt suffixes some strings with a "#" marker (e.g. "AVAILABLE-0072#");
    # strip it (and any trailing space) so the format regexes still anchor.
    text = re.sub(r"\s+", " ", raw.strip().upper()).rstrip(" #")

    for token in _NOT_BOOKABLE_TOKENS:
        if token in text:
            return ParsedAvailability(raw=raw, status=AvailabilityStatus.NOT_BOOKABLE)

    if m := _AVAILABLE_RE.match(text):
        seats = int(m.group(1)) if m.group(1) else None
        if seats == 0:
            # IRCTC emits "AVAILABLE-0000" when the quota exists but has no
            # berths left — bookable in name only; never recommend it.
            return ParsedAvailability(raw=raw, status=AvailabilityStatus.NOT_BOOKABLE)
        label = f"AVL {seats}" if seats else "AVL"
        return ParsedAvailability(raw=label, status=AvailabilityStatus.AVAILABLE)

    if m := _CURR_AVL_RE.match(text):
        seats = int(m.group(1)) if m.group(1) else None
        if seats == 0:
            return ParsedAvailability(raw=raw, status=AvailabilityStatus.NOT_BOOKABLE)
        label = f"AVL {seats}" if seats else "AVL"
        return ParsedAvailability(raw=label, status=AvailabilityStatus.AVAILABLE)

    # "WL3/AVAILABLE": the WL series exists but a booking made now confirms.
    if _HYBRID_AVAILABLE_RE.search(text):
        return ParsedAvailability(raw="AVL", status=AvailabilityStatus.AVAILABLE)

    if m := _RAC_RE.match(text):
        current = int(m.group(2) or m.group(1))
        return ParsedAvailability(raw=f"RAC {current}", status=AvailabilityStatus.RAC)

    if m := _WL_RE.match(text):
        current = int(m.group(1))
        return ParsedAvailability(
            raw=f"WL {current}", status=AvailabilityStatus.WAITLIST
        )

    if m := _WL_RAC_RE.match(text):
        current = int(m.group(1))
        return ParsedAvailability(raw=f"RAC {current}", status=AvailabilityStatus.RAC)

    # Bare "WL 7" (some aggregators) — general series by convention.
    if m := _BARE_WL_RE.match(text):
        current = int(m.group(1))
        return ParsedAvailability(
            raw=f"WL {current}", status=AvailabilityStatus.WAITLIST
        )

    return ParsedAvailability(raw=raw, status=AvailabilityStatus.UNKNOWN)


def extract_json_data(body_str: str) -> dict | None:
    try:
        payload = json.loads(body_str)
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            return payload["data"]
    except (json.JSONDecodeError, TypeError):
        return None


def parse_verify_result(body_str: str) -> dict | None:
    """Parse an IRCTC live-availability response into availability/fare/prediction.

    Returns a dict with 'availability', 'fare', and optional 'prediction_pct',
    or None if the payload is invalid or missing availability info.
    """
    data = extract_json_data(body_str)
    if not data:
        return None

    try:
        live_day = data["avlDayList"][0]
        live_status = live_day["availablityStatus"]
    except (KeyError, IndexError, TypeError):
        return None

    if not live_status:
        return None

    fare_info = data.get("fareInfo")
    fare = fare_info.get("totalFare") if isinstance(fare_info, dict) else None

    result: dict = {
        "availability": parse_availability(live_status),
        "fare": int(round(fare)) if isinstance(fare, (int, float)) else None,  # noqa: RUF046
    }

    try:
        result["prediction_pct"] = int(live_day["predictionPercentage"])
    except (KeyError, ValueError, TypeError):
        pass

    return result
