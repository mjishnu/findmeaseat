"""Async HTTP client for the unofficial endpoints the legacy site used.

  erail.in        -> train header + route (the ~-delimited text protocol)
  confirmtkt.com  -> per-class availability + fare (JSON)

These are third-party aggregators, NOT the official IRCTC API: they rate-limit,
occasionally answer "try again after some time", and can change format without
notice. Every public method therefore retries with backoff and raises
ProviderUnavailableError on persistent failure, so the service layer can map it
to a 503 instead of returning silently-wrong data.

Two LRU-bounded caches keep a single search cheap, both single-flighted so
concurrent callers for the same key share ONE network call (a pair's
get_seat_status + get_fare collapse into one confirmtkt request; concurrent
first-time lookups of one train collapse into one erail fetch):
  * route_cache   — routes rarely change (long TTL; short negative TTL)
  * segment_cache — one confirmtkt response per (src, dst, date) (short TTL)
A Semaphore caps total concurrent outbound requests to stay polite upstream.
"""
import asyncio
import datetime as dt
import re
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable

import httpx

from app.exceptions import ProviderUnavailableError
from app.schemas import BookingQuota

ERAIL_GET_TRAINS = "https://erail.in/rail/getTrains.aspx"
ERAIL_DATA = "https://erail.in/data.aspx"
CONFIRMTKT_SEARCH = "https://cttrainsapi.confirmtkt.com/api/v1/trains/search"
_RETRY_MARKER = "try again after some time"


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


class IRCTCClient:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        retries: int = 3,
        backoff: float = 1.5,
        concurrency: int = 8,
        route_ttl: float = 3600.0,
        route_negative_ttl: float = 60.0,  # short: a transient "not found" self-heals fast
        segment_ttl: float = 60.0,
        route_cache_max: int = 4096,
        segment_cache_max: int = 2048,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=15.0, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True
        )
        self._owns_client = client is None
        self._retries = retries
        self._backoff = backoff
        self._semaphore = asyncio.Semaphore(concurrency)

        self._route_ttl = route_ttl
        self._route_negative_ttl = route_negative_ttl
        self._segment_ttl = segment_ttl
        self._route_cache_max = route_cache_max
        self._segment_cache_max = segment_cache_max
        # LRU-bounded (OrderedDict + move_to_end on use, popitem(last=False) on overflow)
        # so a long-running process can't grow these without limit.
        self._route_cache: OrderedDict[str, tuple[float, dict[str, Any] | None]] = OrderedDict()
        self._segment_cache: OrderedDict[tuple[str, str, str], tuple[float, list[dict]]] = OrderedDict()
        self._segment_inflight: dict[tuple[str, str, str], asyncio.Future] = {}
        self._route_inflight: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _store_route(self, key: str, value: dict[str, Any] | None) -> None:
        self._route_cache[key] = (time.monotonic(), value)
        self._route_cache.move_to_end(key)
        while len(self._route_cache) > self._route_cache_max:
            self._route_cache.popitem(last=False)

    async def _run_single_flight(
        self,
        key: Any,
        inflight: dict,
        compute: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Collapse concurrent callers for `key` into a single `compute()` run;
        waiters share the owner's result/exception.

        If the OWNER task is cancelled (e.g. client disconnect), waiters — which
        were NOT cancelled — must not inherit that CancelledError. They instead
        get a retriable ProviderUnavailableError, and only the owner re-raises
        its own cancellation. This matters because the client is a process-wide
        singleton, so owner and waiters can belong to different HTTP requests.
        """
        async with self._lock:
            fut = inflight.get(key)
            owner = fut is None
            if owner:
                fut = asyncio.get_running_loop().create_future()
                inflight[key] = fut

        if not owner:
            assert fut is not None
            return await fut

        assert fut is not None
        try:
            result = await compute()
        except asyncio.CancelledError:
            async with self._lock:
                inflight.pop(key, None)
            if not fut.done():
                fut.set_exception(ProviderUnavailableError("upstream request cancelled"))
                fut.exception()  # mark retrieved — a waiter may not exist
            raise
        except BaseException as exc:  # share real provider/transport errors
            async with self._lock:
                inflight.pop(key, None)
            if not fut.done():
                fut.set_exception(exc)
            fut.exception()
            raise
        async with self._lock:
            inflight.pop(key, None)
        if not fut.done():
            fut.set_result(result)
        return result

    # --------------------------------------------------------------- transport
    async def _request(
        self, url: str, params: dict, *, soft_retry_marker: str | None = None
    ) -> httpx.Response:
        last: Exception | str | None = None
        for attempt in range(self._retries):
            if attempt:
                await asyncio.sleep(self._backoff * attempt)
            try:
                async with self._semaphore:
                    resp = await self._client.get(url, params=params)
                resp.raise_for_status()
                # The "try again" sentinel is an erail text-protocol quirk; only
                # the text path opts into scanning for it. Never scan confirmtkt
                # JSON, where the phrase could legitimately appear in a note.
                if soft_retry_marker and soft_retry_marker in resp.text:
                    last = "soft-retry"
                    continue
                return resp
            except httpx.HTTPError as exc:
                last = exc
        raise ProviderUnavailableError(
            f"GET {url} failed after {self._retries} attempts ({last})"
        )

    async def _get_text(self, url: str, params: dict) -> str:
        return (await self._request(url, params, soft_retry_marker=_RETRY_MARKER)).text

    async def _get_json(self, url: str, params: dict) -> Any:
        resp = await self._request(url, params)
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderUnavailableError(f"GET {url} returned non-JSON ({exc})") from exc

    # ------------------------------------------------------------------- route
    async def fetch_route(self, train_number: str) -> dict[str, Any] | None:
        """erail header + TRAINROUTE -> {train_no, train_name, stops:[...]} or
        None when the train genuinely does not exist. Single-flighted so
        concurrent first-time lookups for one train share a single erail fetch."""
        now = time.monotonic()
        hit = self._route_cache.get(train_number)
        if hit is not None:
            # Negative (None) entries expire fast so a transient/garbled
            # "train not found" doesn't pin a real train as absent for an hour.
            ttl = self._route_ttl if hit[1] is not None else self._route_negative_ttl
            if now - hit[0] < ttl:
                self._route_cache.move_to_end(train_number)
                return hit[1]

        return await self._run_single_flight(
            train_number,
            self._route_inflight,
            lambda: self._fetch_route_uncached(train_number),
        )

    async def _fetch_route_uncached(self, train_number: str) -> dict[str, Any] | None:
        body = await self._get_text(
            ERAIL_GET_TRAINS,
            {"TrainNo": train_number, "DataSource": 0, "Language": 0, "Cache": "true"},
        )
        if "train not found" in body.lower():
            self._store_route(train_number, None)
            return None

        try:
            segs = body.split("~~~~~~~~")
            d1 = _clean(segs[0])
            if len(d1[1]) > 6:  # erail sometimes prepends an extra field
                d1 = d1[1:]
            d2 = _clean(segs[1])
            train_id = d2[12]
            train_no = d1[1].replace("^", "")
            train_name = d1[2]
        except (IndexError, ValueError) as exc:
            raise ProviderUnavailableError(f"unexpected erail train format ({exc})") from exc

        route_text = await self._get_text(
            ERAIL_DATA,
            {"Action": "TRAINROUTE", "Password": 2012, "Data1": train_id,
             "Data2": 0, "Cache": "true"},
        )
        stops: list[dict[str, Any]] = []
        for item in route_text.split("~^"):
            det = _clean(item)
            if len(det) < 10:
                continue
            distance = _to_int(det[6])
            if distance is None:
                continue
            stops.append({"code": det[1], "name": det[2], "distance_km": distance})

        if not stops:
            raise ProviderUnavailableError("erail TRAINROUTE returned no parseable stops")

        result = {"train_no": train_no, "train_name": train_name, "stops": stops}
        self._store_route(train_number, result)
        return result

    # ----------------------------------------------------------- segment search
    async def search_segment(self, source: str, destination: str, date_ddmmyyyy: str) -> list[dict]:
        """confirmtkt trainList for one segment+date. Cached with single-flight
        so concurrent callers for the same key share one HTTP request."""
        key = (source, destination, date_ddmmyyyy)
        now = time.monotonic()
        async with self._lock:
            hit = self._segment_cache.get(key)
            if hit and now - hit[0] < self._segment_ttl:
                self._segment_cache.move_to_end(key)
                return hit[1]

        async def _compute() -> list[dict]:
            result = await self._do_search(source, destination, date_ddmmyyyy)
            async with self._lock:
                self._segment_cache[key] = (time.monotonic(), result)
                self._segment_cache.move_to_end(key)
                while len(self._segment_cache) > self._segment_cache_max:
                    self._segment_cache.popitem(last=False)
            return result

        return await self._run_single_flight(key, self._segment_inflight, _compute)

    async def _do_search(self, source: str, destination: str, date_ddmmyyyy: str) -> list[dict]:
        payload = await self._get_json(
            CONFIRMTKT_SEARCH,
            {
                "sourceStationCode": source, "destinationStationCode": destination,
                "dateOfJourney": date_ddmmyyyy, "addAvailabilityCache": "true",
                "excludeMultiTicketAlternates": "false", "excludeBoostAlternates": "false",
                "sortBy": "DEFAULT", "enableNearby": "true", "enableTG": "true",
                "tGPlan": "CTG-3", "showTGPrediction": "false",
                "tgColor": "DEFAULT", "showPredictionGlobal": "true",
            },
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        train_list = (data or {}).get("trainList") if isinstance(data, dict) else None
        return train_list or []


def find_train(train_list: list[dict], train_number: str) -> dict | None:
    target = str(train_number)
    for train in train_list:
        if str(train.get("trainNumber")) == target:
            return train
    return None


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
    the general cache; Tatkal reads the bundled `availabilityCacheTatkal`."""
    cache = train.get(cache_key(quota)) or {}
    return cache.get(class_code) or {}


def format_date(journey_date: dt.date) -> str:
    return journey_date.strftime("%d-%m-%Y")
