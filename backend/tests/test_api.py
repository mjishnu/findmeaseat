import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_provider
from app.main import app
from app.services.recommendations import booking_day_today
from tests.conftest import StubProvider, tomorrow

STATUSES = {
    ("C", "D"): "PQWL 10/WL 8",
    ("A", "D"): "GNWL 15/WL 10",
    ("A", "F"): "AVAILABLE 10",
}

client = TestClient(app)


@pytest.fixture()
def stubbed():
    app.dependency_overrides[get_provider] = lambda: StubProvider(STATUSES)
    yield
    app.dependency_overrides.clear()


def _search(**overrides) -> dict:
    params = {
        "train_number": "12345",
        "user_source": "C",
        "user_destination": "D",
        "date": tomorrow().isoformat(),
    } | overrides
    return {"params": params}


def test_happy_path_returns_ranked_recommendations(stubbed):
    res = client.get("/api/find-optimal-route", **_search())
    assert res.status_code == 200
    body = res.json()
    assert body["train_name"] == "Demo Express"
    assert body["pairs_evaluated"] == 9
    legs = [(r["book_from"], r["book_to"]) for r in body["recommendations"]]
    assert legs == [("A", "F"), ("A", "D"), ("C", "D")]
    top = body["recommendations"][0]
    assert top["action"].startswith("Book A to F, board at C")
    assert top["requires_boarding_change"] is True
    assert top["availability"]["status"] == "AVAILABLE"


def test_works_with_real_mock_provider_end_to_end():
    # No override: exercises MockRailDataProvider through the full stack.
    res = client.get("/api/find-optimal-route", **_search())
    assert res.status_code == 200
    body = res.json()
    assert body["pairs_evaluated"] == 9
    scores = [r["score"] for r in body["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    assert len(body["recommendations"]) <= 3


def test_unknown_train_404(stubbed):
    res = client.get("/api/find-optimal-route", **_search(train_number="99999"))
    assert res.status_code == 404
    assert "99999" in res.json()["detail"]


def test_invalid_station_400(stubbed):
    res = client.get("/api/find-optimal-route", **_search(user_source="Z"))
    assert res.status_code == 400
    assert "not on this train's route" in res.json()["detail"]


def test_reversed_direction_400(stubbed):
    res = client.get("/api/find-optimal-route", **_search(user_source="D", user_destination="C"))
    assert res.status_code == 400


def test_past_date_400(stubbed):
    res = client.get(
        "/api/find-optimal-route",
        **_search(date=(booking_day_today() - dt.timedelta(days=1)).isoformat()),
    )
    assert res.status_code == 400


def test_malformed_date_422(stubbed):
    res = client.get("/api/find-optimal-route", **_search(date="2026-13-99"))
    assert res.status_code == 422


def test_malformed_train_number_422(stubbed):
    res = client.get("/api/find-optimal-route", **_search(train_number="12AB5"))
    assert res.status_code == 422


def test_train_route_endpoint(stubbed):
    res = client.get("/api/trains/12345")
    assert res.status_code == 200
    assert [s["code"] for s in res.json()["stations"]] == ["A", "B", "C", "D", "E", "F"]
    assert client.get("/api/trains/99999").status_code == 404
