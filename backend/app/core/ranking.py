"""Confirmation-probability from confirmtkt's per-class prediction + the
distance-penalized score.

The waitlist chance is confirmtkt's own `predictionPercentage` (trained on real
per-class/route/season clearance), not a local heuristic. AVAILABLE and RAC keep
fixed status priors — a seat in hand is a fact, not a prediction. A waitlist with
no upstream estimate returns -1.0 (sentinel: ranks last, flagged as MISSING_PREDICTION).
"""

import math

from app.schemas import AvailabilityStatus, ParsedAvailability

P_AVAILABLE = 0.99
P_RAC = 0.95
COST_PENALTY_WEIGHT = 0.10


def confirmation_probability(
    parsed: ParsedAvailability, prediction_pct: int | None = None
) -> float:
    """Returns the probability of diff booking statuses; -1 means no estimate."""
    if parsed.status is AvailabilityStatus.AVAILABLE:
        return P_AVAILABLE
    if parsed.status is AvailabilityStatus.RAC:
        return P_RAC
    if parsed.status is AvailabilityStatus.WAITLIST and prediction_pct is not None:
        return prediction_pct / 100.0  # We first sort by status (98% WL < 95% RAC)
    return -1.0


def option_score(
    probability: float,
    extra_fare: int | None,
    user_leg_fare: int | None,
    extra_km: int,
    user_leg_km: int,
) -> float:
    """Within-tier score: probability minus a concave fare penalty."""
    if probability < 0:
        return -1.0

    if extra_fare is not None and user_leg_fare:
        ratio = extra_fare / user_leg_fare
    elif user_leg_km:
        ratio = extra_km / user_leg_km
    else:
        return probability

    return max(0.0, probability - COST_PENALTY_WEIGHT * math.sqrt(ratio))
