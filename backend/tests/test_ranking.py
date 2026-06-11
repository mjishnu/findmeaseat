import pytest

from app.core.ranking import confirmation_probability, option_score
from app.schemas import AvailabilityStatus as S
from app.schemas import ParsedAvailability, Quota


def _wl(quota: Quota, current: int) -> ParsedAvailability:
    return ParsedAvailability(
        raw="x", status=S.WAITLIST, quota=quota, series_wl=current, current_wl=current
    )


def _status(status: S, **kw) -> ParsedAvailability:
    return ParsedAvailability(raw="x", status=status, **kw)


def test_priority_hierarchy_available_gnwl_rlwl_pqwl():
    available = confirmation_probability(_status(S.AVAILABLE, seats=5))
    rac = confirmation_probability(_status(S.RAC, current_wl=3))
    gnwl = confirmation_probability(_wl(Quota.GNWL, 5))
    rlwl = confirmation_probability(_wl(Quota.RLWL, 5))
    pqwl = confirmation_probability(_wl(Quota.PQWL, 5))
    assert available > rac > gnwl > rlwl > pqwl > 0


def test_same_quota_lower_waitlist_ranks_higher():
    assert confirmation_probability(_wl(Quota.GNWL, 2)) > confirmation_probability(
        _wl(Quota.GNWL, 10)
    )
    # Strictly monotonic across the whole curve — no banding cliffs
    probs = [confirmation_probability(_wl(Quota.GNWL, wl)) for wl in (1, 8, 15, 25, 45, 80, 150)]
    assert probs == sorted(probs, reverse=True)


def test_unbookable_statuses_score_zero():
    assert confirmation_probability(_status(S.NOT_BOOKABLE)) == 0.0
    assert confirmation_probability(_status(S.UNKNOWN)) == 0.0


def test_no_penalty_for_exact_leg():
    assert option_score(0.85, extra_km=0, user_leg_km=170) == 0.85


def test_distance_penalty_grows_concavely():
    base = 0.85
    near = option_score(base, extra_km=170, user_leg_km=170)    # 2× distance booked
    far = option_score(base, extra_km=680, user_leg_km=170)     # 5× distance booked
    assert base > near > far
    # Concave: quadrupling the extra distance only doubles the penalty (sqrt)
    assert (base - far) == pytest.approx(2 * (base - near))


def test_earlier_origin_wins_only_when_significantly_better():
    # GNWL 5 booked 310 km early still beats RLWL 2 on the exact leg…
    gnwl_early = option_score(
        confirmation_probability(_wl(Quota.GNWL, 5)), extra_km=310, user_leg_km=170
    )
    rlwl_exact = option_score(
        confirmation_probability(_wl(Quota.RLWL, 2)), extra_km=0, user_leg_km=170
    )
    assert gnwl_early > rlwl_exact
    # …but a marginal same-quota improvement does NOT justify the distance cost.
    gnwl_far = option_score(
        confirmation_probability(_wl(Quota.GNWL, 8)), extra_km=850, user_leg_km=170
    )
    gnwl_exact = option_score(
        confirmation_probability(_wl(Quota.GNWL, 10)), extra_km=0, user_leg_km=170
    )
    assert gnwl_exact > gnwl_far


def test_score_clamped_at_zero():
    assert option_score(0.05, extra_km=8000, user_leg_km=100) == 0.0
