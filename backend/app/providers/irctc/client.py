"""Client-side fetch helpers for building requests and parsing raw responses.

  erail.in        -> train header + route (the ~-delimited text protocol)
  confirmtkt.com  -> per-class availability + fare (JSON)

These are third-party aggregators. The browser fetches them directly, and the
server only builds the URLs and parses the results.
"""
import datetime as dt
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


def _clean(segment: str) -> list[str]:
    return [x for x in segment.split("~") if x != ""]


# First signed numeric token: keeps a leading sign and refuses to fuse separate
# numbers (e.g. "1245 + 30 GST" -> 1245, not 124530).
_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _to_int(value: str | int | float | None) -> int | None:
    """Coerce a distance/fare ('120', '₹520', '1,245', -50) to int, else None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(value))
    m = _NUM_RE.search(str(value))
    if m is None:
        return None
    try:
        return int(round(float(m.group().replace(",", ""))))
    except ValueError:
        return None


def parse_erail_header(body: str) -> tuple[str, str, str] | None:
    """Parse erail getTrains response → (train_id, train_no, train_name),
    or None if train not found."""
    if "train not found" in body.lower():
        return None
    segs = body.split("~~~~~~~~")
    d1 = _clean(segs[0])
    if len(d1[1]) > 6:
        d1 = d1[1:]
    d2 = _clean(segs[1])
    return d2[12], d1[1].replace("^", ""), d1[2]


def parse_erail_route(route_text: str) -> list[dict[str, Any]]:
    """Parse erail TRAINROUTE response → list of {code, name, distance_km}."""
    stops = []
    for item in route_text.split("~^"):
        det = _clean(item)
        if len(det) < 10:
            continue
        distance = _to_int(det[6])
        if distance is None:
            continue
        stops.append({"code": det[1], "name": det[2], "distance_km": distance})
    return stops


_BROWSER_HEADERS: dict[str, str] = {} # Browser will automatically set User-Agent

def build_erail_header_descriptor(train_number: str) -> FetchDescriptor:
    params = urlencode({"TrainNo": train_number, "DataSource": 0, "Language": 0, "Cache": "true"})
    return FetchDescriptor(url=f"{ERAIL_GET_TRAINS}?{params}",
                           headers=_BROWSER_HEADERS, fetch_id="erail_header")


def build_erail_route_descriptor(train_id: str) -> FetchDescriptor:
    params = urlencode({"Action": "TRAINROUTE", "Password": 2012,
                        "Data1": train_id, "Data2": 0, "Cache": "true"})
    return FetchDescriptor(url=f"{ERAIL_DATA}?{params}",
                           headers=_BROWSER_HEADERS, fetch_id="erail_route")


def build_confirmtkt_descriptor(
    source: str, destination: str, date: dt.date, quota: BookingQuota, fetch_id: str,
) -> FetchDescriptor:
    params = {
        "sourceStationCode": source, "destinationStationCode": destination,
        "dateOfJourney": format_date(date), "addAvailabilityCache": "true",
        "excludeMultiTicketAlternates": "false", "excludeBoostAlternates": "false",
        "sortBy": "DEFAULT", "enableNearby": "true", "enableTG": "true",
        "tGPlan": "CTG-3", "showTGPrediction": "false",
        "tgColor": "DEFAULT", "showPredictionGlobal": "true",
    }
    # quota= param is required for LD/SS; GN/TQ are bundled without it.
    if quota in (BookingQuota.LADIES, BookingQuota.SENIOR):
        params["quota"] = quota.value
    return FetchDescriptor(url=f"{CONFIRMTKT_SEARCH}?{urlencode(params)}",
                           headers=_BROWSER_HEADERS, fetch_id=fetch_id)


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
        headers=_BROWSER_HEADERS,
        fetch_id=fetch_id,
        method="POST",
    )


# confirmtkt cache key per quota: GN/TQ are bundled on the train object; LD/SS land
# in a single availabilityCacheForQuota filled by a quota=-parameterised search.
_QUOTA_CACHE_KEY = {
    BookingQuota.GENERAL: "availabilityCache",
    BookingQuota.TATKAL: "availabilityCacheTatkal",
    BookingQuota.LADIES: "availabilityCacheForQuota",
    BookingQuota.SENIOR: "availabilityCacheForQuota",
}


def cache_key(quota: BookingQuota) -> str:
    """The confirmtkt train-dict key holding this quota's per-class cache."""
    return _QUOTA_CACHE_KEY[quota]


def class_cache(
    train: dict, class_code: str, quota: BookingQuota = BookingQuota.GENERAL
) -> dict:
    """The availability cache entry for one class in `quota`, or {}. Defaults to
    the general cache; Tatkal reads the bundled `availabilityCacheTatkal`; LD/SS
    read `availabilityCacheForQuota` (filled by a quota=-parameterised search)."""
    cache = train.get(cache_key(quota)) or {}
    return cache.get(class_code) or {}


def format_date(journey_date: dt.date) -> str:
    return journey_date.strftime("%d-%m-%Y")
