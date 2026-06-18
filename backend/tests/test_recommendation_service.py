import asyncio
import datetime as dt

import pytest

from app.exceptions import (
    InvalidJourneyDateError,
    InvalidStationError,
    ProviderUnavailableError,
    TrainNotFoundError,
)
from app.schemas import AvailabilityStatus, BookingQuota, TravelClass
from app.services.recommendations import RecommendationService, booking_day_today
from tests.conftest import StubProvider, tomorrow

# Hand-computed expectation (cost-penalized; user-leg fare = calculate_fare(170) = 205):
#   A→F AVAILABLE: 0.99 − 0.10·√(870/205) ≈ 0.784   (booked 1020 km → fare 1075)
#   A→D GNWL wl10: 0.868 − 0.10·√(345/205) ≈ 0.738  (booked 480 km → fare 550)
#   C→D PQWL wl8:  0.875 × 0.35            ≈ 0.306   (exact leg, no extra fare)
STATUSES = {
    ("C", "D"): "PQWL 10/WL 8",
    ("A", "D"): "GNWL 15/WL 10",
    ("A", "F"): "AVAILABLE 10",
}


@pytest.fixture()
def service() -> RecommendationService:
    return RecommendationService(StubProvider(STATUSES))


async def test_ranks_better_quota_from_earlier_station_first(service):
    res = await service.find_optimal_route("12345", "C", "D", tomorrow())
    legs = [(r.book_from, r.book_to) for r in res.recommendations]
    assert legs == [("A", "F"), ("A", "D"), ("C", "D")]
    assert [r.rank for r in res.recommendations] == [1, 2, 3]
    scores = [r.score for r in res.recommendations]
    assert scores == sorted(scores, reverse=True)


async def test_action_strings_explain_the_booking(service):
    res = await service.find_optimal_route("12345", "C", "D", tomorrow())
    by_leg = {(r.book_from, r.book_to): r for r in res.recommendations}
    assert (
        by_leg[("A", "F")].action
        == "Book A to F, board at C, alight at D. Status: AVAILABLE (10 seats)"
    )
    assert by_leg[("A", "D")].action == "Book A to D, board at C. Status: GNWL 10"
    assert by_leg[("C", "D")].action == "Book C to D, board at C. Status: PQWL 8"


async def test_boarding_change_and_refund_notes(service):
    res = await service.find_optimal_route("12345", "C", "D", tomorrow())
    early = next(r for r in res.recommendations if r.book_from == "A" and r.book_to == "D")
    assert early.requires_boarding_change is True
    assert any("boarding point" in n.lower() for n in early.notes)
    assert any("not refundable" in n.lower() for n in early.notes)
    exact = next(r for r in res.recommendations if (r.book_from, r.book_to) == ("C", "D"))
    assert exact.requires_boarding_change is False
    assert exact.extra_km == 0 and exact.extra_fare == 0


async def test_user_leg_echoes_baseline_status(service):
    res = await service.find_optimal_route("12345", "C", "D", tomorrow())
    assert res.user_leg.availability is not None
    assert res.user_leg.availability.raw == "PQWL 10/WL 8"
    assert res.user_leg.distance_km == 170
    assert res.pairs_evaluated == 9


async def test_travel_class_is_echoed():
    service = RecommendationService(StubProvider(STATUSES))
    res = await service.find_optimal_route("12345", "C", "D", tomorrow(), TravelClass.AC2)
    assert res.travel_class is TravelClass.AC2
    # Defaulted when omitted.
    res_default = await service.find_optimal_route("12345", "C", "D", tomorrow())
    assert res_default.travel_class is TravelClass.SL


async def test_at_most_three_recommendations():
    everything_open = {
        (s, d): "AVAILABLE 5"
        for s in "ABC"
        for d in "DEF"
    }
    service = RecommendationService(StubProvider(everything_open))
    res = await service.find_optimal_route("12345", "C", "D", tomorrow())
    assert len(res.recommendations) == 3


async def test_unbookable_pairs_are_excluded():
    service = RecommendationService(StubProvider({}))  # every pair → REGRET
    res = await service.find_optimal_route("12345", "C", "D", tomorrow())
    assert res.recommendations == []
    # The user's own leg must still echo its (unbookable) status — the capture
    # happens regardless of the NOT_BOOKABLE skip, and this guards that.
    assert res.user_leg.availability is not None
    assert res.user_leg.availability.raw == "REGRET"
    assert res.user_leg.availability.status is AvailabilityStatus.NOT_BOOKABLE


async def test_unknown_train_raises(service):
    with pytest.raises(TrainNotFoundError):
        await service.find_optimal_route("99999", "C", "D", tomorrow())


async def test_invalid_station_raises(service):
    with pytest.raises(InvalidStationError):
        await service.find_optimal_route("12345", "C", "Q", tomorrow())


async def test_station_input_is_normalized(service):
    res = await service.find_optimal_route("12345", " c ", "d", tomorrow())
    assert res.user_leg.source == "C" and res.user_leg.destination == "D"


async def test_past_and_far_future_dates_rejected(service):
    today = booking_day_today()
    with pytest.raises(InvalidJourneyDateError, match="past"):
        await service.find_optimal_route("12345", "C", "D", today - dt.timedelta(days=1))
    with pytest.raises(InvalidJourneyDateError, match="advance reservation"):
        await service.find_optimal_route("12345", "C", "D", today + dt.timedelta(days=61))


class _FlakyProvider(StubProvider):
    """Raises a chosen exception for one (board, alight) pair; normal otherwise."""

    def __init__(self, statuses, fail_pair, exc):
        super().__init__(statuses)
        self._fail_pair = fail_pair
        self._exc = exc

    async def get_seat_status(
        self, train_number, source, destination, journey_date, travel_class,
        quota=BookingQuota.GENERAL,
    ):
        if (source, destination) == self._fail_pair:
            raise self._exc
        return await super().get_seat_status(
            train_number, source, destination, journey_date, travel_class, quota
        )


async def test_one_pair_upstream_failure_degrades_instead_of_503():
    # One alternate pair (A→F) hits a transient upstream error; the search must
    # still return the surviving pairs rather than failing the whole request.
    provider = _FlakyProvider(STATUSES, ("A", "F"), ProviderUnavailableError("flaky upstream"))
    res = await RecommendationService(provider).find_optimal_route("12345", "C", "D", tomorrow())
    legs = [(r.book_from, r.book_to) for r in res.recommendations]
    assert ("A", "F") not in legs                       # the failed pair is dropped
    assert ("A", "D") in legs and ("C", "D") in legs    # survivors still ranked
    assert res.pairs_skipped == 1
    assert res.pairs_evaluated == 9


async def test_unexpected_pair_error_is_not_masked():
    # A non-provider error is a real bug and must propagate, not be swallowed.
    provider = _FlakyProvider(STATUSES, ("A", "D"), ValueError("genuine bug"))
    with pytest.raises(ValueError):
        await RecommendationService(provider).find_optimal_route("12345", "C", "D", tomorrow())


async def test_stray_cancellation_on_one_pair_is_degraded_not_500():
    # A stray CancelledError inherited from a shared single-flight owner must not
    # 500 a healthy request — it degrades to a skipped pair (this task itself was
    # never cancelled, so gather returns it as a result rather than raising).
    provider = _FlakyProvider(STATUSES, ("A", "F"), asyncio.CancelledError())
    res = await RecommendationService(provider).find_optimal_route("12345", "C", "D", tomorrow())
    assert res.pairs_skipped == 1
    legs = [(r.book_from, r.book_to) for r in res.recommendations]
    assert ("A", "F") not in legs
    assert ("A", "D") in legs and ("C", "D") in legs


class _EqualFareProvider(StubProvider):
    """Every booking costs the same — mimics IR's coarse fare brackets where a
    slightly longer leg falls in the same slab (the real 2A case reported)."""

    async def get_fare(self, *args, **kwargs):
        return 500


async def test_same_fare_lower_waitlist_earlier_station_ranks_first():
    # Regression: a lower-waitlist booking from an earlier station at the SAME
    # fare must outrank the higher-waitlist direct leg (it didn't under the old
    # distance penalty). C→D is the user's leg; B is one stop earlier.
    statuses = {("C", "D"): "GNWL 8/WL 7", ("B", "D"): "GNWL 6/WL 5"}
    service = RecommendationService(_EqualFareProvider(statuses))
    res = await service.find_optimal_route("12345", "C", "D", tomorrow())
    top = res.recommendations[0]
    assert (top.book_from, top.book_to) == ("B", "D")   # WL5 earlier-station wins
    assert top.availability.current_wl == 5
    assert top.extra_fare == 0
    direct = next(r for r in res.recommendations if (r.book_from, r.book_to) == ("C", "D"))
    assert direct.availability.current_wl == 7
    assert res.recommendations.index(direct) > 0          # the WL7 direct ranks below


async def test_class_alternative_shows_best_odds_across_pairs_not_direct_leg():
    # Bug fix: the searched SL leg is departed, but SL via an earlier station is
    # WL25; 1A is WL3 direct yet AVAILABLE from the earliest station. The banner
    # must show 1A's BEST achievable odds (AVAILABLE), not its direct-leg WL3.
    statuses = {
        ("C", "D", "SL"): "Train Departed",   # searched class, direct: departed
        ("B", "D", "SL"): "GNWL 30/WL 25",    # but bookable one stop earlier
        ("C", "D", "1A"): "GNWL 5/WL 3",      # 1A direct: WL3
        ("A", "D", "1A"): "AVAILABLE 5",      # 1A from the origin: a seat!
    }
    provider = StubProvider(statuses, class_options={"SL": 175, "1A": 1190})
    res = await RecommendationService(provider).find_optimal_route(
        "12345", "C", "D", tomorrow(), TravelClass.SL
    )
    assert [a.travel_class for a in res.alternatives] == [TravelClass.AC1]
    alt = res.alternatives[0]
    assert alt.quota is BookingQuota.GENERAL                          # same quota, class switch
    assert alt.availability.status is AvailabilityStatus.AVAILABLE  # not WAITLIST/WL3
    assert alt.probability == pytest.approx(0.99)


async def test_no_alternatives_when_searched_cell_can_get_a_seat():
    # SL is AVAILABLE from the origin (best chance 0.99); nothing can beat it.
    statuses = {
        ("A", "D", "SL"): "AVAILABLE 5",
        ("C", "D", "SL"): "GNWL 5/WL 3",
        ("C", "D", "2A"): "AVAILABLE 10",  # 2A also available, but not > 0.99
    }
    provider = StubProvider(statuses, class_options={"SL": 175, "2A": 1900})
    res = await RecommendationService(provider).find_optimal_route(
        "12345", "C", "D", tomorrow(), TravelClass.SL
    )
    assert res.alternatives == []


async def test_quota_is_echoed_and_defaults_to_general():
    service = RecommendationService(StubProvider(STATUSES))
    res = await service.find_optimal_route(
        "12345", "C", "D", tomorrow(), TravelClass.SL, BookingQuota.TATKAL
    )
    assert res.quota is BookingQuota.TATKAL
    res_default = await service.find_optimal_route("12345", "C", "D", tomorrow())
    assert res_default.quota is BookingQuota.GENERAL


async def test_tatkal_recommendations_mention_the_quota():
    # When the user searches Tatkal, the action line / notes must say so.
    service = RecommendationService(StubProvider(STATUSES))
    res = await service.find_optimal_route(
        "12345", "C", "D", tomorrow(), TravelClass.SL, BookingQuota.TATKAL
    )
    assert res.recommendations
    top = res.recommendations[0]
    assert "Tatkal quota" in top.action
    assert any("Tatkal" in n for n in top.notes)


async def test_alternatives_surface_a_cross_quota_switch():
    # Searched GN·SL is waitlisted on every covering pair; TQ·3A has a seat.
    # The banner must propose switching BOTH axes at once (Tatkal · 3A).
    statuses = {
        ("C", "D", "SL", "GN"): "GNWL 20/WL 18",
        ("A", "D", "SL", "GN"): "GNWL 22/WL 15",
        ("C", "D", "3A", "TQ"): "AVAILABLE 5",
    }
    provider = StubProvider(
        statuses,
        class_options={"SL": 175, "3A": 1190},
        tatkal_class_options={"SL": 250, "3A": 1500},
    )
    res = await RecommendationService(provider).find_optimal_route(
        "12345", "C", "D", tomorrow(), TravelClass.SL, BookingQuota.GENERAL
    )
    assert len(res.alternatives) == 1
    alt = res.alternatives[0]
    assert alt.quota is BookingQuota.TATKAL
    assert alt.travel_class is TravelClass.AC3
    assert alt.availability.status is AvailabilityStatus.AVAILABLE
    assert alt.fare is not None  # priced (StubProvider fares are distance-based)


async def test_no_tatkal_alternatives_when_tatkal_is_empty():
    # Distant date → Tatkal offers nothing → no TQ cells surface, only class
    # switches within the searched General quota.
    statuses = {
        ("C", "D", "SL", "GN"): "GNWL 20/WL 18",
        ("A", "D", "3A", "GN"): "AVAILABLE 5",
    }
    provider = StubProvider(
        statuses,
        class_options={"SL": 175, "3A": 1190},
        tatkal_class_options={},  # Tatkal window not open
    )
    res = await RecommendationService(provider).find_optimal_route(
        "12345", "C", "D", tomorrow(), TravelClass.SL, BookingQuota.GENERAL
    )
    assert all(a.quota is BookingQuota.GENERAL for a in res.alternatives)
    assert [a.travel_class for a in res.alternatives] == [TravelClass.AC3]


async def test_alternatives_capped_at_three_and_sorted_by_probability():
    # Many strictly-better cells across the grid; keep only the top 3, best first.
    statuses = {
        ("C", "D", "SL", "GN"): "GNWL 40/WL 38",  # searched: poor odds
        ("C", "D", "3A", "GN"): "GNWL 10/WL 6",
        ("C", "D", "2A", "GN"): "GNWL 8/WL 4",
        ("C", "D", "1A", "GN"): "RAC 3",
        ("C", "D", "SL", "TQ"): "AVAILABLE 9",
        ("C", "D", "3A", "TQ"): "AVAILABLE 5",
    }
    provider = StubProvider(
        statuses,
        class_options={"SL": 175, "3A": 1190, "2A": 1900, "1A": 2600},
        tatkal_class_options={"SL": 250, "3A": 1500},
    )
    res = await RecommendationService(provider).find_optimal_route(
        "12345", "C", "D", tomorrow(), TravelClass.SL, BookingQuota.GENERAL
    )
    assert len(res.alternatives) == 3
    probs = [a.probability for a in res.alternatives]
    assert probs == sorted(probs, reverse=True)
    # The two Tatkal AVAILABLE cells (prob 0.99) outrank every waitlisted cell.
    assert res.alternatives[0].availability.status is AvailabilityStatus.AVAILABLE


class _NoFareProvider(StubProvider):
    async def get_fare(self, *args, **kwargs):
        return None  # upstream didn't price this class anywhere


async def test_missing_fare_yields_none_not_zero():
    provider = _NoFareProvider({("C", "D"): "AVAILABLE 5", ("A", "F"): "AVAILABLE 5"})
    res = await RecommendationService(provider).find_optimal_route("12345", "C", "D", tomorrow())
    assert res.user_leg.fare is None
    for r in res.recommendations:
        assert r.fare is None
        assert r.extra_fare is None                       # not a negative number
        assert not any("Costs" in n for n in r.notes)     # no misleading cost note


async def test_ladies_quota_recommendation_carries_ladies_note_and_action():
    provider = StubProvider({("A", "F"): "AVAILABLE 5"})
    res = await RecommendationService(provider).find_optimal_route(
        "12345", "A", "F", tomorrow(), TravelClass.SL, BookingQuota.LADIES
    )
    assert res.quota is BookingQuota.LADIES
    assert any("Ladies quota" in n for rec in res.recommendations for n in rec.notes)
    assert any("in Ladies quota" in rec.action for rec in res.recommendations)
