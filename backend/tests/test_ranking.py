import pytest

from app.core.ranking import P_AVAILABLE, P_RAC, confirmation_probability, option_score
from app.schemas import AvailabilityStatus as S
from app.schemas import ParsedAvailability, Quota


def _wl(current: int = 5, quota: Quota = Quota.GNWL) -> ParsedAvailability:
    return ParsedAvailability(raw="x", status=S.WAITLIST, quota=quota, current_wl=current)


def _status(status: S, **kw) -> ParsedAvailability:
    return ParsedAvailability(raw="x", status=status, **kw)


def test_waitlist_uses_confirmtkt_prediction():
    assert confirmation_probability(_wl(), prediction_pct=81) == pytest.approx(0.81)
    # A real 0 is a genuine (very low) estimate, NOT "no estimate".
    assert confirmation_probability(_wl(), prediction_pct=0) == 0.0


def test_waitlist_without_prediction_is_none():
    assert confirmation_probability(_wl(), prediction_pct=None) is None
    assert confirmation_probability(_wl()) is None  # default


def test_class_is_no_longer_inferred_from_waitlist_number():
    # Same prediction -> same probability regardless of the WL number (the old
    # WL-curve is gone; confirmtkt's per-class number is the only signal).
    assert confirmation_probability(_wl(3), 70) == confirmation_probability(_wl(40), 70)


def test_available_and_rac_use_status_priors_regardless_of_prediction():
    assert confirmation_probability(_status(S.AVAILABLE, seats=5)) == P_AVAILABLE
    assert confirmation_probability(_status(S.AVAILABLE, seats=5), prediction_pct=10) == P_AVAILABLE
    assert confirmation_probability(_status(S.RAC, current_wl=3)) == P_RAC


def test_unbookable_statuses_score_zero():
    assert confirmation_probability(_status(S.NOT_BOOKABLE)) == 0.0
    assert confirmation_probability(_status(S.UNKNOWN)) == 0.0


def test_option_score_is_none_when_probability_is_none():
    assert option_score(None, extra_fare=0, user_leg_fare=205, extra_km=0, user_leg_km=170) is None


def test_no_penalty_for_exact_leg():
    assert option_score(0.85, extra_fare=0, user_leg_fare=205, extra_km=0, user_leg_km=170) == 0.85


def test_same_fare_is_not_penalized_for_distance():
    assert option_score(0.85, extra_fare=0, user_leg_fare=205, extra_km=190, user_leg_km=170) == 0.85


def test_cost_penalty_grows_concavely():
    base = 0.85
    near = option_score(base, extra_fare=205, user_leg_fare=205, extra_km=0, user_leg_km=170)
    far = option_score(base, extra_fare=820, user_leg_fare=205, extra_km=0, user_leg_km=170)
    assert base > near > far
    assert (base - far) == pytest.approx(2 * (base - near))


def test_distance_proxy_used_when_fare_unknown():
    penalized = option_score(0.85, extra_fare=None, user_leg_fare=None, extra_km=170, user_leg_km=170)
    assert penalized == pytest.approx(0.85 - 0.10)


def test_score_clamped_at_zero():
    assert option_score(0.05, extra_fare=8000, user_leg_fare=100, extra_km=0, user_leg_km=100) == 0.0
