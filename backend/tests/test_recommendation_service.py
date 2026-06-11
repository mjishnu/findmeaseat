import datetime as dt

import pytest

from app.exceptions import InvalidJourneyDateError, InvalidStationError, TrainNotFoundError
from app.schemas import AvailabilityStatus
from app.services.recommendations import RecommendationService, booking_day_today
from tests.conftest import StubProvider, tomorrow

# Hand-computed expectation (see plan Decision Log #5):
#   A→F AVAILABLE: 0.99 − 0.10·√(850/170) ≈ 0.766
#   A→D GNWL wl10: 0.868 − 0.10·√(310/170) ≈ 0.733
#   C→D PQWL wl8:  0.875 × 0.35           ≈ 0.306
STATUSES = {
    ("C", "D"): "PQWL 10/WL 8",
    ("A", "D"): "GNWL 15/WL 10",
    ("A", "F"): "AVAILABLE 10",
}


@pytest.fixture()
def service() -> RecommendationService:
    return RecommendationService(StubProvider(STATUSES))


def test_ranks_better_quota_from_earlier_station_first(service):
    res = service.find_optimal_route("12345", "C", "D", tomorrow())
    legs = [(r.book_from, r.book_to) for r in res.recommendations]
    assert legs == [("A", "F"), ("A", "D"), ("C", "D")]
    assert [r.rank for r in res.recommendations] == [1, 2, 3]
    scores = [r.score for r in res.recommendations]
    assert scores == sorted(scores, reverse=True)


def test_action_strings_explain_the_booking(service):
    res = service.find_optimal_route("12345", "C", "D", tomorrow())
    by_leg = {(r.book_from, r.book_to): r for r in res.recommendations}
    assert (
        by_leg[("A", "F")].action
        == "Book A to F, board at C, alight at D. Status: AVAILABLE (10 seats)"
    )
    assert by_leg[("A", "D")].action == "Book A to D, board at C. Status: GNWL 10"
    assert by_leg[("C", "D")].action == "Book C to D, board at C. Status: PQWL 8"


def test_boarding_change_and_refund_notes(service):
    res = service.find_optimal_route("12345", "C", "D", tomorrow())
    early = next(r for r in res.recommendations if r.book_from == "A" and r.book_to == "D")
    assert early.requires_boarding_change is True
    assert any("boarding point" in n.lower() for n in early.notes)
    assert any("not refundable" in n.lower() for n in early.notes)
    exact = next(r for r in res.recommendations if (r.book_from, r.book_to) == ("C", "D"))
    assert exact.requires_boarding_change is False
    assert exact.extra_km == 0 and exact.extra_fare == 0


def test_user_leg_echoes_baseline_status(service):
    res = service.find_optimal_route("12345", "C", "D", tomorrow())
    assert res.user_leg.availability is not None
    assert res.user_leg.availability.raw == "PQWL 10/WL 8"
    assert res.user_leg.distance_km == 170
    assert res.pairs_evaluated == 9


def test_at_most_three_recommendations():
    everything_open = {
        (s, d): "AVAILABLE 5"
        for s in "ABC"
        for d in "DEF"
    }
    service = RecommendationService(StubProvider(everything_open))
    res = service.find_optimal_route("12345", "C", "D", tomorrow())
    assert len(res.recommendations) == 3


def test_unbookable_pairs_are_excluded():
    service = RecommendationService(StubProvider({}))  # every pair → REGRET
    res = service.find_optimal_route("12345", "C", "D", tomorrow())
    assert res.recommendations == []
    # The user's own leg must still echo its (unbookable) status — the capture
    # happens before the NOT_BOOKABLE skip, and this guards that ordering.
    assert res.user_leg.availability is not None
    assert res.user_leg.availability.raw == "REGRET"
    assert res.user_leg.availability.status is AvailabilityStatus.NOT_BOOKABLE


def test_unknown_train_raises(service):
    with pytest.raises(TrainNotFoundError):
        service.find_optimal_route("99999", "C", "D", tomorrow())


def test_invalid_station_raises(service):
    with pytest.raises(InvalidStationError):
        service.find_optimal_route("12345", "C", "Q", tomorrow())


def test_station_input_is_normalized(service):
    res = service.find_optimal_route("12345", " c ", "d", tomorrow())
    assert res.user_leg.source == "C" and res.user_leg.destination == "D"


def test_past_and_far_future_dates_rejected(service):
    today = booking_day_today()
    with pytest.raises(InvalidJourneyDateError, match="past"):
        service.find_optimal_route("12345", "C", "D", today - dt.timedelta(days=1))
    with pytest.raises(InvalidJourneyDateError, match="advance reservation"):
        service.find_optimal_route("12345", "C", "D", today + dt.timedelta(days=61))
