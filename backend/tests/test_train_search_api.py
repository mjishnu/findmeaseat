"""HTTP layer for train search: /api/trains-between and /api/stations."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_provider, get_station_directory
from app.exceptions import ProviderUnavailableError
from app.main import app
from app.schemas import RawClassOffer, RawTrainBetween, Station, TravelClass
from app.services.stations import StationDirectory
from tests.conftest import tomorrow

client = TestClient(app)

_RAW_TRAIN = RawTrainBetween(
    train_number="12952",
    train_name="MUMBAI RAJDHANI",
    from_code="NDLS",
    from_name="New Delhi",
    to_code="BCT",
    to_name="Mumbai Central",
    departure_time="16:25",
    arrival_time="08:15",
    duration_min=950,
    running_days="1111111",
    has_pantry=True,
    distance_km=1384,
    general_offers=[
        RawClassOffer(travel_class=TravelClass.AC3, raw_availability="AVAILABLE-0042", fare=1980),
        RawClassOffer(travel_class=TravelClass.SL, raw_availability="RLWL3/WL3", fare=755),
    ],
    tatkal_offers=[
        RawClassOffer(travel_class=TravelClass.SL, raw_availability="NOT AVAILABLE", fare=0),
    ],
)

_DIR = StationDirectory([
    Station(code="NDLS", name="New Delhi", city="New Delhi"),
    Station(code="BCT", name="Mumbai Central", city="Mumbai"),
    Station(code="CSTM", name="Mumbai Csmt", city="Mumbai"),
])


class _TrainsProvider:
    def __init__(self, trains=None, raises=None):
        self._trains = trains or []
        self._raises = raises

    async def search_trains_between(self, source, destination, journey_date):
        if self._raises is not None:
            raise self._raises
        return self._trains


def _override(provider) -> None:
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_station_directory] = lambda: _DIR


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    app.dependency_overrides.clear()


def _params(**overrides) -> dict:
    return {"params": {"source": "ndls", "destination": "bct",
                       "date": tomorrow().isoformat()} | overrides}


def test_trains_between_happy_path():
    _override(_TrainsProvider([_RAW_TRAIN]))
    res = client.get("/api/trains-between", **_params())
    assert res.status_code == 200
    body = res.json()
    assert (body["source"], body["destination"]) == ("NDLS", "BCT")
    [train] = body["trains"]
    assert train["train_number"] == "12952"
    assert [c["travel_class"] for c in train["general"]] == ["3A", "SL"]
    assert train["general"][0]["availability"]["status"] == "AVAILABLE"


def test_trains_between_tatkal_zero_fare_is_null():
    _override(_TrainsProvider([_RAW_TRAIN]))
    body = client.get("/api/trains-between", **_params()).json()
    tatkal_sl = body["trains"][0]["tatkal"][0]
    assert tatkal_sl["fare"] is None
    assert tatkal_sl["availability"]["status"] == "NOT_BOOKABLE"


def test_trains_between_empty_is_200():
    _override(_TrainsProvider([]))
    res = client.get("/api/trains-between", **_params())
    assert res.status_code == 200
    assert res.json()["trains"] == []


def test_trains_between_past_date_400():
    _override(_TrainsProvider([_RAW_TRAIN]))
    res = client.get(
        "/api/trains-between",
        **_params(date=(tomorrow() - dt.timedelta(days=2)).isoformat()),
    )
    assert res.status_code == 400


def test_trains_between_malformed_date_422():
    _override(_TrainsProvider([_RAW_TRAIN]))
    res = client.get("/api/trains-between", **_params(date="2026-13-99"))
    assert res.status_code == 422


def test_trains_between_upstream_failure_503():
    _override(_TrainsProvider(raises=ProviderUnavailableError()))
    res = client.get("/api/trains-between", **_params())
    assert res.status_code == 503


def test_stations_search_happy():
    _override(_TrainsProvider())
    res = client.get("/api/stations", params={"q": "mum"})
    assert res.status_code == 200
    codes = {s["code"] for s in res.json()}
    assert {"BCT", "CSTM"} <= codes
    assert "NDLS" not in codes


def test_stations_blank_query_422():
    _override(_TrainsProvider())
    assert client.get("/api/stations", params={"q": ""}).status_code == 422


def test_stations_limit_respected():
    _override(_TrainsProvider())
    res = client.get("/api/stations", params={"q": "m", "limit": 1})
    assert res.status_code == 200
    assert len(res.json()) <= 1


class _QuotaProvider:
    def __init__(self, rows=None, raises=None):
        self._rows = rows or []
        self._raises = raises

    async def search_quota_availability(self, source, destination, journey_date, quota):
        if self._raises is not None:
            raise self._raises
        return self._rows


def test_trains_between_quota_happy_path():
    rows = [("12952", "NDLS", "16:25", [
        RawClassOffer(travel_class=TravelClass.SL, raw_availability="AVAILABLE-0010", fare=755),
    ])]
    _override(_QuotaProvider(rows))
    res = client.get("/api/trains-between/quota", **_params(quota="LD"))
    assert res.status_code == 200
    body = res.json()
    assert body["quota"] == "LD"
    [train] = body["trains"]
    assert (train["train_number"], train["from_code"], train["departure_time"]) == ("12952", "NDLS", "16:25")
    assert train["classes"][0]["availability"]["status"] == "AVAILABLE"


def test_trains_between_quota_unknown_quota_422():
    _override(_QuotaProvider())
    res = client.get("/api/trains-between/quota", **_params(quota="ZZ"))
    assert res.status_code == 422
