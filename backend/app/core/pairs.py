from app.exceptions import InvalidStationError, ProviderUnavailableError
from app.schemas import StationStop, TrainRoute


def enumerate_pairs(
    route: TrainRoute,
    source: str,
    destination: str,
    partial: bool = False,
    min_coverage_pct: float = 1.0,
    require_connect: bool = True,
) -> list[tuple[StationStop, StationStop]]:
    """Generate candidate (board, alight) station pairs for a train route.

    Always includes full-coverage pairs (board <= source AND alight >= destination).
    If `partial=True`, also includes partial-coverage pairs whose overlap with
    the user's journey is >= `min_coverage_pct`.
    """
    stations = route.stations
    codes = [station.code for station in stations]

    if source not in codes or destination not in codes:
        raise InvalidStationError(
            f"Station is not on this train's route ({' → '.join(codes)})"
        )

    src_idx, dst_idx = codes.index(source), codes.index(destination)
    if src_idx >= dst_idx:
        raise InvalidStationError("Source or destination are invalid")

    user_leg_km = stations[dst_idx].distance_km - stations[src_idx].distance_km
    if user_leg_km <= 0:
        raise ProviderUnavailableError(
            "Route station distance data is missing or invalid"
        )

    # Fast path: Full coverage pairs
    covering_pairs = [
        (b, a) for b in stations[: src_idx + 1] for a in stations[dst_idx:]
    ]
    if not partial:
        return covering_pairs

    # Partial coverage pairs
    n = len(stations)
    for i in range(n):
        for j in range(i + 1, n):
            # Skip full-coverage pairs (already included above)
            if i <= src_idx and j >= dst_idx:
                continue
            # Connection check: pair must touch source or destination
            if require_connect and not (i <= src_idx <= j or i <= dst_idx <= j):
                continue

            # Overlap & coverage check
            start, end = max(i, src_idx), min(j, dst_idx)
            if start < end:
                overlap_km = stations[end].distance_km - stations[start].distance_km
                if (overlap_km / user_leg_km) >= min_coverage_pct:
                    covering_pairs.append((stations[i], stations[j]))

    return covering_pairs
