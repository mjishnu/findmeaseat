import math
import re

from app.schemas import AvailabilityStatus, Candidate, ParsedAvailability

P_AVAILABLE = 0.99
P_RAC = 0.95
COST_PENALTY_WEIGHT = 0.10


def compute_extra_fare(fare: int, user_leg_fare: int) -> int:
    if fare <= 0 or user_leg_fare <= 0:
        return 0
    return max(0, fare - user_leg_fare)


def confirmation_probability(
    parsed: ParsedAvailability, prediction_pct: int = -1
) -> float:
    """Returns the probability of diff booking statuses; -1 means no estimate."""
    if parsed.status is AvailabilityStatus.AVAILABLE:
        return P_AVAILABLE
    if parsed.status is AvailabilityStatus.RAC:
        return P_RAC
    if parsed.status is AvailabilityStatus.WAITLIST and prediction_pct != -1:
        return prediction_pct / 100.0  # We first sort by status (98% WL < 95% RAC)
    return -1.0


def sort_candidates(
    candidates: list[Candidate], user_leg_fare: int, user_leg_km: int
) -> tuple[list[Candidate], Candidate | None, tuple | None]:
    """Sorts candidates descending by rank score and returns (sorted_list, best_candidate, best_key)."""
    if not candidates:
        return [], None, None

    def _sort_key(c: Candidate) -> tuple:
        if c.probability < 0:
            score = -1.0
        elif c.extra_fare >= 0 and user_leg_fare > 0:
            ratio = c.extra_fare / user_leg_fare
            base_score = max(
                0.0, c.probability - COST_PENALTY_WEIGHT * math.sqrt(ratio)
            )
            score = base_score * c.coverage_pct
        elif user_leg_km:
            ratio = c.extra_km / user_leg_km
            base_score = max(
                0.0, c.probability - COST_PENALTY_WEIGHT * math.sqrt(ratio)
            )
            score = base_score * c.coverage_pct
        else:
            score = c.probability * c.coverage_pct

        m = re.search(r"\d+", c.parsed.raw)
        num = int(m.group()) if m else 0
        queue_score = -num if c.parsed.status == AvailabilityStatus.WAITLIST else num
        return (
            round(score, 4),
            c.parsed.status,
            c.coverage_pct,
            queue_score,
            -c.extra_km,
        )

    keyed = [(_sort_key(c), c) for c in candidates]
    keyed.sort(key=lambda item: item[0], reverse=True)

    sorted_candidates = [c for _, c in keyed]
    best_candidate_key, best_candidate = keyed[0]
    return sorted_candidates, best_candidate, best_candidate_key
