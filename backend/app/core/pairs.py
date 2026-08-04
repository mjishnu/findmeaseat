from app.exceptions import InvalidStationError
from app.schemas import StationStop, TrainRoute


def enumerate_covering_pairs(
    route: TrainRoute, source: str, destination: str
) -> list[tuple[StationStop, StationStop]]:
    """Generate all possible board and alight (get off point) in a train route"""

    codes = [stop.code for stop in route.stations]
    if source not in codes or destination not in codes:
        raise InvalidStationError(
            f"Station is not on this train's route ({' → '.join(codes)})"
        )
    s, d = codes.index(source), codes.index(destination)
    if s >= d:
        raise InvalidStationError("Source or destination are invalid")
    boards = route.stations[: s + 1]  # board at the source or any earlier stop
    alights = route.stations[d:]  # alight at the destination or any later stop
    return [(b, a) for b in boards for a in alights]


def enumerate_partial_pairs(
    route: TrainRoute,
    source: str,
    destination: str,
    min_coverage_pct: float,
    require_connect: bool = True,
) -> list[tuple[StationStop, StationStop]]:
    """Generate partial-coverage pairs whose overlap with the user's journey
    covers ≥ *min_coverage_pct* of the user's leg distance.

    Excludes full-coverage pairs (board ≤ source AND alight ≥ dest) since
    those are already produced by :func:`enumerate_covering_pairs`.

    When *require_connect* is True only pairs where the user's source **or**
    destination station falls within ``[board, alight]`` are kept.
    """

    codes = [stop.code for stop in route.stations]
    if source not in codes or destination not in codes:
        raise InvalidStationError(
            f"Station is not on this train's route ({' → '.join(codes)})"
        )
    src_idx = codes.index(source)
    dst_idx = codes.index(destination)
    if src_idx >= dst_idx:
        raise InvalidStationError("Source or destination are invalid")

    km = {stop.code: stop.distance_km for stop in route.stations}
    user_leg_km = km[destination] - km[source]
    if user_leg_km <= 0:
        return []

    n = len(route.stations)
    results: list[tuple[StationStop, StationStop]] = []

    for i in range(n):
        for j in range(i + 1, n):
            # Skip full-coverage pairs — enumerate_covering_pairs handles them
            if i <= src_idx and j >= dst_idx:
                continue

            # Compute overlap with the user's journey
            overlap_start = max(i, src_idx)
            overlap_end = min(j, dst_idx)
            if overlap_start >= overlap_end:
                continue  # no overlap with user's journey

            overlap_km = km[codes[overlap_end]] - km[codes[overlap_start]]
            coverage = overlap_km / user_leg_km
            if coverage < min_coverage_pct:
                continue

            # Connect filter: pair must touch source or destination
            if require_connect:
                source_connected = i <= src_idx <= j
                dest_connected = i <= dst_idx <= j
                if not (source_connected or dest_connected):
                    continue

            results.append((route.stations[i], route.stations[j]))

    return results
