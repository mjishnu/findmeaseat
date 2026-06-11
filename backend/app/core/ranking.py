"""Confirmation-probability heuristics and the distance-penalized score.

The numbers are PRIORS distilled from public waitlist-clearance patterns
(ConfirmTkt-style bands), not official figures — they are named constants
precisely so they can be tuned or replaced by a learned model later.
"""
import math

from app.schemas import AvailabilityStatus, ParsedAvailability, Quota

P_AVAILABLE = 0.99
P_RAC = 0.95  # RAC guarantees travel (shared berth) — better than every waitlist

# Piecewise-linear curve over the CURRENT waitlist number (the second number
# in "GNWL15/WL10"). Linear interpolation keeps ranking strictly monotonic:
# a lower waitlist number always scores higher within the same quota.
_WL_CURVE: list[tuple[int, float]] = [(1, 0.90), (15, 0.85), (30, 0.55), (60, 0.25), (100, 0.08)]

# Relative clearance odds by quota type. GNWL clears from the whole train's
# cancellation pool; RLWL from one remote-location quota; PQWL from a single
# pooled quota shared by many station pairs; RQWL is the last resort.
QUOTA_FACTOR: dict[Quota, float] = {
    Quota.GNWL: 1.0,
    Quota.RLWL: 0.5,
    Quota.RSWL: 0.4,
    Quota.PQWL: 0.35,
    Quota.TQWL: 0.3,
    Quota.RQWL: 0.2,
}

# Weight of the telescopic-fare distance penalty in option_score.
DISTANCE_PENALTY_WEIGHT = 0.10


def _wl_probability(current_wl: int) -> float:
    points = _WL_CURVE
    if current_wl <= points[0][0]:
        return points[0][1]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if current_wl <= x2:
            return y1 + (y2 - y1) * (current_wl - x1) / (x2 - x1)
    return points[-1][1]


def confirmation_probability(parsed: ParsedAvailability) -> float:
    """Probability that booking this status ends in a confirmed (or RAC) berth."""
    if parsed.status is AvailabilityStatus.AVAILABLE:
        return P_AVAILABLE
    if parsed.status is AvailabilityStatus.RAC:
        return P_RAC
    if parsed.status is AvailabilityStatus.WAITLIST and parsed.quota and parsed.current_wl:
        return _wl_probability(parsed.current_wl) * QUOTA_FACTOR[parsed.quota]
    return 0.0  # NOT_BOOKABLE / UNKNOWN / malformed waitlist


def option_score(probability: float, extra_km: int, user_leg_km: int) -> float:
    """Probability minus a concave distance penalty.

    Fares are telescopic (per-km rate falls with distance), so the cost of
    booking a longer leg grows sub-linearly — sqrt mirrors that. The penalty
    means an earlier origin only outranks the exact leg when it brings a
    SIGNIFICANTLY better confirmation chance.
    """
    if extra_km <= 0:
        return probability
    penalty = DISTANCE_PENALTY_WEIGHT * math.sqrt(extra_km / user_leg_km)
    return max(0.0, probability - penalty)
