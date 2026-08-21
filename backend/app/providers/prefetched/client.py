"""Client-side fetch helpers for building requests and parsing raw responses.

  erail.in        -> train header + route (the ~-delimited text protocol)
  confirmtkt.com  -> per-class availability + fare (JSON)

These are third-party aggregators. The browser fetches them directly, and the
server only builds the URLs and parses the results.
"""

import datetime as dt
import json
import re
from typing import Any
from urllib.parse import urlencode

from app.schemas import BookingQuota, FetchDescriptor, TravelClass

ERAIL_GET_TRAINS = "https://erail.in/rail/getTrains.aspx"
ERAIL_DATA = "https://erail.in/data.aspx"
CONFIRMTKT_SEARCH = "https://cttrainsapi.confirmtkt.com/api/v1/trains/search"
CONFIRMTKT_AVAILABILITY = (
    "https://cttrainsapi.confirmtkt.com/api/v1/availability/fetchAvailability"
)


# First signed numeric token: keeps a leading sign and refuses to fuse separate
# numbers (e.g. "1245 + 30 GST" -> 1245, not 124530 (30 GST is skipped for simplicity)).
_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def to_int(value: str | float | None) -> int:
    """Coerce a distance/fare ('120', '₹520', '1,245', -50) to int, else -1."""
    if value is None:
        return -1
    if isinstance(value, (int, float)):
        return int(round(value))  # noqa: RUF046
    m = _NUM_RE.search(str(value))
    if m is None:
        return -1
    try:
        return int(round(float(m.group().replace(",", ""))))  # noqa: RUF046
    except ValueError:
        return -1


def parse_erail_header(body: str) -> dict[str, Any] | None:
    """Parse client-stripped erail header JSON → dict with train_id, train_name, running_days, classes."""
    if not body:
        return None
    try:
        data = json.loads(body)
        if isinstance(data, dict) and "train_id" in data and "train_name" in data:
            return {
                "train_id": str(data["train_id"]),
                "train_name": str(data["train_name"]),
                "running_days": str(data.get("running_days") or "1111111"),
                "classes": list(data.get("classes") or []),
            }
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def parse_erail_route(route_text: str) -> list[dict[str, Any]]:
    """Parse client-stripped erail route JSON → list of {code, name, distance_km}."""
    if not route_text:
        return []
    try:
        data = json.loads(route_text)
        if isinstance(data, dict) and isinstance(data.get("stops"), list):
            return data["stops"]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def build_erail_header_descriptor(train_number: str) -> FetchDescriptor:
    params = urlencode(
        {"TrainNo": train_number, "DataSource": 0, "Language": 0, "Cache": "true"}
    )
    return FetchDescriptor(url=f"{ERAIL_GET_TRAINS}?{params}", fetch_id="erail_header")


def build_erail_route_descriptor(train_id: str) -> FetchDescriptor:
    params = urlencode(
        {
            "Action": "TRAINROUTE",
            "Password": 2012,
            "Data1": train_id,
            "Data2": 0,
            "Cache": "true",
        }
    )
    return FetchDescriptor(url=f"{ERAIL_DATA}?{params}", fetch_id="erail_route")


def build_confirmtkt_descriptor(
    source: str,
    destination: str,
    date: dt.date,
    quota: BookingQuota,
    fetch_id: str,
) -> FetchDescriptor:
    params = {
        "sourceStationCode": source,
        "destinationStationCode": destination,
        "dateOfJourney": format_date(date),
        "addAvailabilityCache": "true",
        "excludeMultiTicketAlternates": "false",
        "excludeBoostAlternates": "false",
        "sortBy": "DEFAULT",
        "enableNearby": "true",
        "enableTG": "true",
        "tGPlan": "CTG-3",
        "showTGPrediction": "false",
        "tgColor": "DEFAULT",
        "showPredictionGlobal": "true",
    }
    # quota= param is required for LD/SS; GN/TQ are bundled without it.
    if quota in (BookingQuota.LADIES, BookingQuota.SENIOR):
        params["quota"] = quota.value
    return FetchDescriptor(
        url=f"{CONFIRMTKT_SEARCH}?{urlencode(params)}", fetch_id=fetch_id
    )


def build_availability_descriptor(
    train_number: str,
    travel_class: TravelClass,
    quota: BookingQuota,
    source: str,
    destination: str,
    date: dt.date,
    fetch_id: str,
) -> FetchDescriptor:
    params = {
        "trainNo": train_number,
        "travelClass": travel_class.value,
        "quota": quota.value,
        "sourceStationCode": source,
        "destinationStationCode": destination,
        "dateOfJourney": format_date(date),
        "enableTG": "true",
        "tGPlan": "CTG-A48",
        "showTGPrediction": "false",
        "tgColor": "DEFAULT",
        "showPredictionGlobal": "true",
        "showNewMealOptions": "true",
        "showNewAlternates": "true",
        "showNewAltText": "true",
    }
    return FetchDescriptor(
        url=f"{CONFIRMTKT_AVAILABILITY}?{urlencode(params)}",
        fetch_id=fetch_id,
        method="POST",
    )


_QUOTA_CACHE_KEY = {
    BookingQuota.GENERAL: "availabilityCache",
    BookingQuota.TATKAL: "availabilityCacheTatkal",
    BookingQuota.LADIES: "availabilityCacheForQuota",
    BookingQuota.SENIOR: "availabilityCacheForQuota",
}


def quota_cache_key(quota: BookingQuota) -> str:
    """The cache key for one class in `quota`"""
    return _QUOTA_CACHE_KEY[quota]


def quota_class_cache(
    train: dict, class_code: str, quota: BookingQuota = BookingQuota.GENERAL
) -> dict:
    """The cache entry for one class in `quota`"""
    cache = train.get(quota_cache_key(quota)) or {}
    return cache.get(class_code) or {}


def format_date(journey_date: dt.date) -> str:
    return journey_date.strftime("%d-%m-%Y")
