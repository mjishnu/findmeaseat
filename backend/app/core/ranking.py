"""Confirmation-probability from confirmtkt's per-class prediction + the
distance-penalized score.

The waitlist chance is confirmtkt's own `predictionPercentage` (trained on real
per-class/route/season clearance), not a local heuristic. AVAILABLE and RAC keep
fixed status priors — a seat in hand is a fact, not a prediction. A waitlist with
no upstream estimate returns None (the caller flags it and ranks it last).
"""
import math

from app.schemas import AvailabilityStatus, ParsedAvailability

P_AVAILABLE = 0.99
P_RAC = 0.95  # RAC guarantees travel (shared berth) — better than every waitlist

# Weight of the concave extra-cost penalty in option_score.
COST_PENALTY_WEIGHT = 0.10


def confirmation_probability(
    parsed: ParsedAvailability, prediction_pct: int | None = None
) -> float | None:
    """Probability that booking this status ends in a confirmed (or RAC) berth.

    Returns None for a waitlist with no confirmtkt estimate — distinct from a real
    0.0 estimate. NOT_BOOKABLE/UNKNOWN return 0.0 (only reachable via train-search;
    the seat-finder drops those pairs before ranking)."""
    if parsed.status is AvailabilityStatus.AVAILABLE:
        return P_AVAILABLE
    if parsed.status is AvailabilityStatus.RAC:
        return P_RAC
    if parsed.status is AvailabilityStatus.WAITLIST:
        if prediction_pct is not None:
            return prediction_pct / 100.0  # confirmtkt's estimate (0 stays 0.0)
        return None
    return 0.0


def option_score(
    probability: float | None,
    extra_fare: int | None,
    user_leg_fare: int | None,
    extra_km: int,
    user_leg_km: int,
) -> float | None:
    """Probability minus a concave penalty on the EXTRA COST of a longer booking.

    Returns None when probability is None (a no-estimate option carries no score).
    The penalty tracks the real fare difference, not raw distance: IR fares are
    telescopic, so a longer booking often costs the same and must not be demoted.
    sqrt keeps it concave; falls back to a distance proxy when the fare is unknown.
    """
    if probability is None:
        return None
    if extra_fare is not None and user_leg_fare:
        ratio = extra_fare / user_leg_fare
    elif user_leg_km:
        ratio = extra_km / user_leg_km
    else:
        ratio = 0.0
    if ratio <= 0:
        return probability
    penalty = COST_PENALTY_WEIGHT * math.sqrt(ratio)
    return max(0.0, probability - penalty)
