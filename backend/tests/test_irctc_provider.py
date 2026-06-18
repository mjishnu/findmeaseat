"""IRCTCRailDataProvider against canned erail/confirmtkt payloads via
httpx.MockTransport — exercises mapping, class selection, raw-string passthrough,
single-flight, and the 503 failure path with NO real network."""
import asyncio
import datetime as dt

import httpx
import pytest

from app.core.parser import parse_availability
from app.exceptions import ProviderUnavailableError
from app.providers.irctc.client import IRCTCClient, _to_int, class_cache
from app.providers.irctc.provider import IRCTCRailDataProvider
from app.schemas import AvailabilityStatus, BookingQuota, TravelClass

DATE = dt.date(2026, 7, 1)

# erail getTrains.aspx: header segment + "~~~~~~~~" + secondary segment (train_id at idx 12).
_SEG0 = "1~12951~Mumbai Rajdhani~Mumbai Central~MMCT~New Delhi~NDLS~0~0~0~0~17.00~08.32~15.32~1111111"
_SEG1 = "a~b~c~d~e~f~g~h~i~j~k~l~16289"
ERAIL_TRAIN_BODY = _SEG0 + "~~~~~~~~" + _SEG1

# erail TRAINROUTE: a header chunk (skipped, <10 fields) then "~^"-joined stops.
ERAIL_ROUTE_BODY = "~^".join(
    [
        "HDR~meta",
        "0~MMCT~Mumbai Central~00.00~17.00~1~0~1~SF~WR",
        "0~BRC~Vadodara Jn~22.13~22.18~1~392~1~SF~WR",
        "0~NDLS~New Delhi~08.32~00.00~2~1384~1~SF~NR",
    ]
)

CT_PAYLOAD = {
    "data": {
        "trainList": [
            {
                "trainNumber": "12951",
                "trainName": "Mumbai Rajdhani",
                "fromStnCode": "MMCT",
                "toStnCode": "NDLS",
                "departureTime": "17:00",
                "arrivalTime": "08:32",
                "duration": 929,
                "avlClassesSorted": ["3A", "2A", "1A"],
                "availabilityCache": {
                    "SL": {"availabilityDisplayName": "AVAILABLE-0042", "fare": 1245, "prediction": "95%"},
                    "3A": {"availabilityDisplayName": "GNWL50/WL30", "fare": 3140, "prediction": "61%"},
                },
                "availabilityCacheTatkal": {},
            }
        ]
    }
}
CT_PAYLOAD_OTHER = {"data": {"trainList": [{"trainNumber": "22222", "availabilityCache": {}}]}}

# Realistic confirmtkt reply: several trains (nearby/alternates) with the target
# 12951 in the MIDDLE, plus an INTEGER trainNumber entry to lock in str() coercion.
CT_PAYLOAD_MULTI = {
    "data": {
        "trainList": [
            {"trainNumber": "12953", "availabilityCache": {"SL": {"availabilityDisplayName": "RAC 5", "fare": 999}}},
            CT_PAYLOAD["data"]["trainList"][0],  # target 12951 (SL 1245 / 3A 3140)
            {"trainNumber": 22222, "availabilityCache": {"SL": {"availabilityDisplayName": "GNWL10/WL4", "fare": 777}}},
        ]
    }
}

# Tatkal cache conflicts with the general cache; the provider must use GENERAL.
CT_PAYLOAD_TATKAL = {
    "data": {
        "trainList": [
            {
                "trainNumber": "12951",
                "availabilityCache": {"SL": {"availabilityDisplayName": "AVAILABLE-0042", "fare": 1245}},
                "availabilityCacheTatkal": {"SL": {"availabilityDisplayName": "WL5/WL2", "fare": 1690}},
            }
        ]
    }
}

# Bookable class whose fare key is absent — get_fare must return None, not 0.
CT_PAYLOAD_NO_FARE = {
    "data": {
        "trainList": [
            {"trainNumber": "12951", "availabilityCache": {"SL": {"availabilityDisplayName": "AVAILABLE-0010"}}}
        ]
    }
}

# Tatkal cache populated with extra classes + a zero-fare unbookable cell. A
# quota=TATKAL read must use availabilityCacheTatkal; a 0 fare coerces to None.
CT_PAYLOAD_TATKAL_RICH = {
    "data": {
        "trainList": [
            {
                "trainNumber": "12951",
                "avlClassesSorted": ["SL", "3A"],
                "availabilityCache": {
                    "SL": {"availabilityDisplayName": "AVAILABLE-0042", "fare": 1245},
                },
                "availabilityCacheTatkal": {
                    "3A": {"availabilityDisplayName": "AVAILABLE-0006", "fare": 1690},
                    "SL": {"availabilityDisplayName": "NOT AVAILABLE", "fare": 0},
                },
            }
        ]
    }
}

# Valid confirmtkt JSON that happens to contain the erail "try again" phrase in a
# note — the JSON path must NOT treat it as a soft-retry sentinel.
CT_PAYLOAD_NOISY = {
    "data": {
        "trainList": [
            {
                "trainNumber": "12951",
                "note": "Please try again after some time.",
                "availabilityCache": {"SL": {"availabilityDisplayName": "AVAILABLE-0042", "fare": 1245}},
            }
        ]
    }
}


def _make_handler(
    *,
    train_body: str = ERAIL_TRAIN_BODY,
    route_body: str = ERAIL_ROUTE_BODY,
    ct_payload: dict = CT_PAYLOAD,
    ct_status: int = 200,
    counter: dict | None = None,
):
    def handle(request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if host == "erail.in" and path == "/rail/getTrains.aspx":
            if counter is not None:
                counter["erail_trains"] = counter.get("erail_trains", 0) + 1
            return httpx.Response(200, text=train_body)
        if host == "erail.in" and path == "/data.aspx":
            if counter is not None:
                counter["erail_route"] = counter.get("erail_route", 0) + 1
            return httpx.Response(200, text=route_body)
        if host == "cttrainsapi.confirmtkt.com":
            if counter is not None:
                counter["ct"] += 1
            if ct_status != 200:
                return httpx.Response(ct_status, text="upstream error")
            return httpx.Response(200, json=ct_payload)
        return httpx.Response(404, text="unexpected url")

    return handle


def _provider(handler, *, retries: int = 1, backoff: float = 0.0):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = IRCTCClient(client=http, retries=retries, backoff=backoff)
    return IRCTCRailDataProvider(client), http


async def test_get_route_maps_stops_and_distances():
    provider, http = _provider(_make_handler())
    try:
        route = await provider.get_route("12951")
    finally:
        await http.aclose()
    assert route is not None
    assert route.train_number == "12951"
    assert route.train_name == "Mumbai Rajdhani"
    assert [s.code for s in route.stations] == ["MMCT", "BRC", "NDLS"]
    assert [s.distance_km for s in route.stations] == [0, 392, 1384]


async def test_get_route_none_when_not_found():
    provider, http = _provider(_make_handler(train_body="~~~~~Train not found"))
    try:
        assert await provider.get_route("00000") is None
    finally:
        await http.aclose()


async def test_get_seat_status_returns_raw_display_string():
    provider, http = _provider(_make_handler())
    try:
        status = await provider.get_seat_status("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
    finally:
        await http.aclose()
    # Raw confirmtkt string — the app's parser owns normalization.
    assert status == "AVAILABLE-0042"
    assert parse_availability(status).status is AvailabilityStatus.AVAILABLE


async def test_class_selection_and_fare():
    provider, http = _provider(_make_handler())
    try:
        status = await provider.get_seat_status("12951", "MMCT", "NDLS", DATE, TravelClass.AC3)
        fare = await provider.get_fare("12951", "MMCT", "NDLS", DATE, TravelClass.AC3)
        sl_fare = await provider.get_fare("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
    finally:
        await http.aclose()
    assert status == "GNWL50/WL30"
    assert fare == 3140
    assert sl_fare == 1245


async def test_unbookable_when_train_absent_on_segment():
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_OTHER))
    try:
        status = await provider.get_seat_status("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
        fare = await provider.get_fare("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
    finally:
        await http.aclose()
    assert status == "NOT AVAILABLE"
    assert parse_availability(status).status is AvailabilityStatus.NOT_BOOKABLE
    assert fare is None  # absent train → unknown fare (not 0, which would read as free)


async def test_single_flight_collapses_status_and_fare_to_one_call():
    counter = {"ct": 0}
    provider, http = _provider(_make_handler(counter=counter))
    try:
        status, fare = await asyncio.gather(
            provider.get_seat_status("12951", "MMCT", "NDLS", DATE, TravelClass.SL),
            provider.get_fare("12951", "MMCT", "NDLS", DATE, TravelClass.SL),
        )
    finally:
        await http.aclose()
    assert status == "AVAILABLE-0042" and fare == 1245
    assert counter["ct"] == 1


async def test_upstream_5xx_raises_503():
    provider, http = _provider(_make_handler(ct_status=500), retries=2)
    try:
        with pytest.raises(ProviderUnavailableError):
            await provider.get_seat_status("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
    finally:
        await http.aclose()


async def test_persistent_try_again_raises_503():
    provider, http = _provider(
        _make_handler(train_body="Please try again after some time."), retries=2
    )
    try:
        with pytest.raises(ProviderUnavailableError):
            await provider.get_route("12951")
    finally:
        await http.aclose()


async def test_selects_target_train_from_multi_train_list():
    # find_train must match by number, not take trainList[0] or [-1].
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_MULTI))
    try:
        status = await provider.get_seat_status("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
        fare = await provider.get_fare("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
    finally:
        await http.aclose()
    assert status == "AVAILABLE-0042"  # 12951's value, not 12953's "RAC 5" / 22222's WL
    assert fare == 1245


async def test_matches_integer_train_number():
    # The entry's trainNumber is the int 22222; str() coercion must still match.
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_MULTI))
    try:
        status = await provider.get_seat_status("22222", "MMCT", "NDLS", DATE, TravelClass.SL)
        fare = await provider.get_fare("22222", "MMCT", "NDLS", DATE, TravelClass.SL)
    finally:
        await http.aclose()
    assert status == "GNWL10/WL4"
    assert fare == 777


async def test_uses_general_quota_not_tatkal():
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_TATKAL))
    try:
        status = await provider.get_seat_status("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
        fare = await provider.get_fare("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
    finally:
        await http.aclose()
    assert status == "AVAILABLE-0042"  # general, not the Tatkal "WL5/WL2"
    assert fare == 1245                 # general, not the Tatkal 1690


async def test_missing_fare_on_bookable_class_returns_none():
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_NO_FARE))
    try:
        status = await provider.get_seat_status("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
        fare = await provider.get_fare("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
    finally:
        await http.aclose()
    assert status == "AVAILABLE-0010"   # bookable
    assert fare is None                 # unknown price, NOT 0


async def test_route_positive_cache_avoids_second_erail_fetch():
    counter = {"ct": 0, "erail_trains": 0, "erail_route": 0}
    provider, http = _provider(_make_handler(counter=counter))
    try:
        first = await provider.get_route("12951")
        second = await provider.get_route("12951")
    finally:
        await http.aclose()
    assert first == second
    assert counter["erail_trains"] == 1  # second call served from cache


async def test_route_negative_cache_avoids_refetch():
    counter = {"ct": 0, "erail_trains": 0, "erail_route": 0}
    provider, http = _provider(_make_handler(train_body="~~~~~Train not found", counter=counter))
    try:
        assert await provider.get_route("00000") is None
        assert await provider.get_route("00000") is None
    finally:
        await http.aclose()
    assert counter["erail_trains"] == 1  # "not found" is negatively cached, not re-fetched


async def test_confirmtkt_json_with_retry_phrase_is_not_discarded():
    # The erail "try again" sentinel must not be matched against confirmtkt JSON.
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_NOISY), retries=1)
    try:
        status = await provider.get_seat_status("12951", "MMCT", "NDLS", DATE, TravelClass.SL)
    finally:
        await http.aclose()
    assert status == "AVAILABLE-0042"  # not discarded/retried into a 503


async def test_owner_cancellation_does_not_poison_waiters():
    # A cancelled single-flight OWNER (e.g. client disconnect) must not propagate
    # CancelledError to an uncancelled WAITER sharing the same segment key.
    http = httpx.AsyncClient(transport=httpx.MockTransport(_make_handler()))
    client = IRCTCClient(client=http)
    started = asyncio.Event()
    release = asyncio.Event()

    async def _blocking_search(source, destination, date):
        started.set()
        await release.wait()
        return []

    client._do_search = _blocking_search  # type: ignore[method-assign]
    try:
        owner = asyncio.create_task(client.search_segment("AAA", "BBB", "01-07-2026"))
        await started.wait()                       # owner is inside compute(), blocked
        waiter = asyncio.create_task(client.search_segment("AAA", "BBB", "01-07-2026"))
        for _ in range(3):                         # let the waiter park on the shared future
            await asyncio.sleep(0)
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner
        with pytest.raises(ProviderUnavailableError):
            await waiter                           # retriable error, NOT CancelledError
    finally:
        release.set()
        await http.aclose()


async def test_get_class_options_returns_all_offered_classes():
    provider, http = _provider(_make_handler())
    try:
        opts = await provider.get_class_options("12951", "MMCT", "NDLS", DATE)
    finally:
        await http.aclose()
    by_class = {code: (status, fare) for code, status, fare in opts}
    assert by_class["SL"] == ("AVAILABLE-0042", 1245)
    assert by_class["3A"] == ("GNWL50/WL30", 3140)


async def test_seat_status_and_fare_read_tatkal_cache_when_quota_tatkal():
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_TATKAL))
    try:
        status = await provider.get_seat_status(
            "12951", "MMCT", "NDLS", DATE, TravelClass.SL, BookingQuota.TATKAL
        )
        fare = await provider.get_fare(
            "12951", "MMCT", "NDLS", DATE, TravelClass.SL, BookingQuota.TATKAL
        )
    finally:
        await http.aclose()
    assert status == "WL5/WL2"  # the Tatkal cell, not the general "AVAILABLE-0042"
    assert fare == 1690         # the Tatkal fare, not the general 1245


async def test_get_class_options_reads_tatkal_cache():
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_TATKAL_RICH))
    try:
        gn = await provider.get_class_options("12951", "MMCT", "NDLS", DATE)
        tq = await provider.get_class_options(
            "12951", "MMCT", "NDLS", DATE, BookingQuota.TATKAL
        )
    finally:
        await http.aclose()
    assert {code for code, _s, _f in gn} == {"SL"}            # general offers SL only
    by_class = {code: (status, fare) for code, status, fare in tq}
    assert by_class["3A"] == ("AVAILABLE-0006", 1690)         # Tatkal-only class surfaces


async def test_tatkal_zero_fare_coerced_to_none():
    provider, http = _provider(_make_handler(ct_payload=CT_PAYLOAD_TATKAL_RICH))
    try:
        fare = await provider.get_fare(
            "12951", "MMCT", "NDLS", DATE, TravelClass.SL, BookingQuota.TATKAL
        )
    finally:
        await http.aclose()
    assert fare is None  # the unbookable Tatkal cell reports 0 → None, never "free"


def test_class_cache_selects_quota_specific_cache():
    train = CT_PAYLOAD_TATKAL["data"]["trainList"][0]
    assert class_cache(train, "SL").get("availabilityDisplayName") == "AVAILABLE-0042"
    assert (
        class_cache(train, "SL", BookingQuota.TATKAL).get("availabilityDisplayName")
        == "WL5/WL2"
    )


_TRAIN_ALL_QUOTAS = {
    "trainNumber": "12951",
    "availabilityCache": {"SL": {"availabilityDisplayName": "AVAILABLE-0042"}},
    "availabilityCacheTatkal": {"SL": {"availabilityDisplayName": "WL5/WL2"}},
    "availabilityCacheForQuota": {"SL": {"availabilityDisplayName": "LADIES WL3"}},
}


def test_class_cache_routes_ladies_and_senior_to_for_quota_cache():
    train = _TRAIN_ALL_QUOTAS
    assert class_cache(train, "SL", BookingQuota.GENERAL).get("availabilityDisplayName") == "AVAILABLE-0042"
    assert class_cache(train, "SL", BookingQuota.TATKAL).get("availabilityDisplayName") == "WL5/WL2"
    assert class_cache(train, "SL", BookingQuota.LADIES).get("availabilityDisplayName") == "LADIES WL3"
    assert class_cache(train, "SL", BookingQuota.SENIOR).get("availabilityDisplayName") == "LADIES WL3"


def test_to_int_keeps_sign_and_first_token():
    assert _to_int("-50") == -50
    assert _to_int("1,245") == 1245
    assert _to_int("₹520") == 520
    assert _to_int("1245 + 30 GST") == 1245  # first token, not fused 124530
    assert _to_int(3140) == 3140
    assert _to_int("") is None
    assert _to_int(None) is None
