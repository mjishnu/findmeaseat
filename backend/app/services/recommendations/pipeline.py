"""Orchestrates search candidate ranking and live verification response building."""

import datetime as dt

from app.domain.dates import validate_journey_date
from app.domain.pairs import enumerate_pairs
from app.domain.ranking import (
    compute_extra_fare,
    confirmation_probability,
    sort_candidates,
)
from app.exceptions import TrainNotFoundError
from app.providers.base import RailDataProvider
from app.schemas import (
    BookingQuota,
    Candidate,
    ParsedAvailability,
    RecommendationResponse,
    StationStop,
    SwitchAlternative,
    TravelClass,
    UserLeg,
)
from app.services.recommendations.evaluator import (
    build_better_alternatives,
    build_recommendation,
    evaluate_class,
)

MAX_VERIFY_CANDIDATES = 10
MAX_RECOMMENDATIONS = 3


async def rank_candidates(
    provider: RailDataProvider,
    train_number: str,
    user_source: str,
    user_destination: str,
    journey_date: dt.date,
    travel_class: TravelClass = TravelClass.SL,
    quota: BookingQuota = BookingQuota.GENERAL,
    partial: bool = False,
    min_coverage_pct: float = 1.0,
    require_connect: bool = True,
) -> dict:
    source = user_source.strip().upper()
    destination = user_destination.strip().upper()
    validate_journey_date(journey_date)

    route = await provider.get_route()
    if route is None:
        raise TrainNotFoundError(train_number)

    pairs = enumerate_pairs(
        route, source, destination, partial, min_coverage_pct, require_connect
    )

    km = {stop.code: stop.distance_km for stop in route.stations}
    user_leg_km = km[destination] - km[source]
    (
        candidates,
        user_leg_parsed,
        pairs_skipped,
        user_leg_fare,
    ) = await evaluate_class(
        provider,
        pairs,
        source,
        destination,
        km,
        user_leg_km,
        travel_class,
        quota,
    )

    # Compute coverage_pct for each candidate
    for c in candidates:
        start_code = c.board.code if km[c.board.code] > km[source] else source
        end_code = (
            c.alight.code if km[c.alight.code] < km[destination] else destination
        )
        c.board_at = start_code
        c.alight_at = end_code
        c.coverage_pct = (km[end_code] - km[start_code]) / user_leg_km

    candidates, chosen_best, chosen_best_key = sort_candidates(
        candidates, user_leg_fare, user_leg_km
    )
    chosen_best_fare = chosen_best.fare if chosen_best else user_leg_fare

    # build alternative in other classes
    alternatives = await build_better_alternatives(
        provider,
        pairs,
        source,
        destination,
        km,
        user_leg_km,
        travel_class,
        quota,
        chosen_best_key,
        chosen_best_fare,
    )

    # Serialize top 10 candidates
    serialized_candidates = [
        {
            "board": c.board.model_dump(),
            "alight": c.alight.model_dump(),
            "parsed": c.parsed.model_dump(),
            "probability": c.probability,
            "extra_km": c.extra_km,
            "fare": c.fare,
            "extra_fare": c.extra_fare,
            "coverage_pct": c.coverage_pct,
            "board_at": c.board_at,
            "alight_at": c.alight_at,
        }
        for c in candidates[:MAX_VERIFY_CANDIDATES]
    ]

    serialized_alternatives = [a.model_dump() for a in alternatives]

    user_leg_dict = {
        "source": source,
        "destination": destination,
        "distance_km": user_leg_km,
        "fare": user_leg_fare,
        "availability": user_leg_parsed.model_dump() if user_leg_parsed else None,
    }

    context = {
        "train_number": route.train_number,
        "train_name": route.train_name,
        "journey_date": journey_date.isoformat(),
        "travel_class": travel_class.value,
        "quota": quota.value,
        "user_leg": user_leg_dict,
        "pairs_evaluated": len(pairs),
        "pairs_skipped": pairs_skipped,
        "partial": partial,
        "min_coverage_pct": min_coverage_pct,
    }

    return {
        "candidates": serialized_candidates,
        "alternatives": serialized_alternatives,
        "context": context,
    }


def build_verified_response(
    ranked_data: dict, live_overrides: dict[str, dict]
) -> RecommendationResponse:
    """Re-rank top-10 candidates with live data, returning the final top-3."""
    context = ranked_data["context"]
    source = context["user_leg"]["source"]
    destination = context["user_leg"]["destination"]
    user_leg_km = context["user_leg"]["distance_km"]
    user_leg_fare = context["user_leg"]["fare"]
    quota = BookingQuota(context["quota"])

    updated_candidates: list[Candidate] = []

    for cand_dict in ranked_data["candidates"]:
        board = StationStop(**cand_dict["board"])
        alight = StationStop(**cand_dict["alight"])
        parsed = ParsedAvailability(**cand_dict["parsed"])
        probability = cand_dict["probability"]
        fare = cand_dict["fare"]

        fetch_id = f"{board.code}|{alight.code}"

        if fetch_id in live_overrides:
            override = live_overrides[fetch_id]
            parsed = override.get("availability", parsed)
            probability = confirmation_probability(
                parsed, override.get("prediction_pct", -1)
            )
            fare = override.get("fare", fare)

        extra_fare = compute_extra_fare(fare, user_leg_fare)

        updated_candidates.append(
            Candidate(
                board=board,
                alight=alight,
                parsed=parsed,
                probability=probability,
                extra_km=cand_dict["extra_km"],
                fare=fare,
                extra_fare=extra_fare,
                coverage_pct=cand_dict.get("coverage_pct", 1.0),
                board_at=cand_dict.get("board_at", ""),
                alight_at=cand_dict.get("alight_at", ""),
            )
        )

    updated_candidates, _, _ = sort_candidates(
        updated_candidates, user_leg_fare, user_leg_km
    )

    recommendations = [
        build_recommendation(rank, cand, source, destination, quota)
        for rank, cand in enumerate(updated_candidates[:MAX_RECOMMENDATIONS], start=1)
    ]

    alternatives = [SwitchAlternative(**a) for a in ranked_data["alternatives"]]
    user_leg = UserLeg(**context["user_leg"])

    return RecommendationResponse(
        train_number=context["train_number"],
        train_name=context["train_name"],
        journey_date=dt.date.fromisoformat(context["journey_date"]),
        travel_class=TravelClass(context["travel_class"]),
        quota=quota,
        user_leg=user_leg,
        pairs_evaluated=context["pairs_evaluated"],
        pairs_skipped=context["pairs_skipped"],
        recommendations=recommendations,
        alternatives=alternatives,
        partial=context.get("partial", False),
        min_coverage_pct=context.get("min_coverage_pct", 1.0),
    )
