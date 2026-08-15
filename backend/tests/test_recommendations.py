import datetime as dt

from app.schemas import (
    AvailabilityStatus,
    BookingQuota,
    Candidate,
    ParsedAvailability,
    RecommendationNoteCode,
    StationStop,
)
from app.services.recommendations.evaluator import (
    MAX_ALTERNATIVES,
    build_recommendation,
)
from app.services.recommendations.pipeline import (
    MAX_RECOMMENDATIONS,
    MAX_VERIFY_CANDIDATES,
    build_verified_response,
)


def test_constants():
    assert MAX_VERIFY_CANDIDATES == 10
    assert MAX_RECOMMENDATIONS == 3
    assert MAX_ALTERNATIVES == 3


def test_build_recommendation_notes():
    board = StationStop(code="SNDD", name="Sanpada", distance_km=10)
    alight = StationStop(code="VSH", name="Vashi", distance_km=20)
    parsed = ParsedAvailability(raw="AVAILABLE 5", status=AvailabilityStatus.AVAILABLE)

    cand = Candidate(
        board=board,
        alight=alight,
        parsed=parsed,
        probability=0.95,
        extra_km=5,
        fare=100,
        extra_fare=20,
        coverage_pct=0.8,
        board_at="SNDD",
        alight_at="VSH",
    )

    rec = build_recommendation(
        rank=1,
        cand=cand,
        source="CSMT",
        destination="VSH",
        quota=BookingQuota.TATKAL,
    )

    assert rec.rank == 1
    assert RecommendationNoteCode.QUOTA_TATKAL in rec.notes
    assert RecommendationNoteCode.EXTRA_FARE in rec.notes
    assert RecommendationNoteCode.BOARDING_CHANGE in rec.notes
    assert RecommendationNoteCode.PARTIAL_COVERAGE in rec.notes


def test_build_verified_response():
    ranked_data = {
        "context": {
            "train_number": "12345",
            "train_name": "Test Express",
            "journey_date": "2026-09-01",
            "travel_class": "SL",
            "quota": "GN",
            "user_leg": {
                "source": "SNDD",
                "destination": "VSH",
                "distance_km": 10,
                "fare": 50,
                "availability": None,
            },
            "pairs_evaluated": 1,
            "pairs_skipped": 0,
        },
        "candidates": [
            {
                "board": {"code": "SNDD", "name": "Sanpada", "distance_km": 10},
                "alight": {"code": "VSH", "name": "Vashi", "distance_km": 20},
                "parsed": {
                    "raw": "AVAILABLE 5",
                    "status": AvailabilityStatus.AVAILABLE,
                },
                "probability": 0.9,
                "extra_km": 0,
                "fare": 50,
                "extra_fare": 0,
                "coverage_pct": 1.0,
                "board_at": "SNDD",
                "alight_at": "VSH",
            }
        ],
        "alternatives": [],
    }

    res = build_verified_response(ranked_data, {})
    assert res.train_number == "12345"
    assert res.train_name == "Test Express"
    assert len(res.recommendations) == 1
    assert res.recommendations[0].book_from == "SNDD"
    assert res.recommendations[0].book_to == "VSH"


def test_parse_verify_result():
    from app.core.parser import parse_verify_result

    # Valid payload
    payload = {
        "data": {
            "avlDayList": [
                {
                    "availablityStatus": "AVAILABLE 10",
                    "predictionPercentage": "85",
                }
            ],
            "fareInfo": {"totalFare": 150.7},
        }
    }
    import json

    res = parse_verify_result(json.dumps(payload))
    assert res is not None
    assert res["availability"].raw == "AVL 10"
    assert res["fare"] == 151
    assert res["prediction_pct"] == 85

    # Invalid / empty payloads return None
    assert parse_verify_result("invalid json") is None
    assert parse_verify_result("{}") is None
    assert parse_verify_result(json.dumps({"data": {}})) is None

