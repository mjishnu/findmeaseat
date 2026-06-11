from app.exceptions import InvalidStationError
from app.schemas import StationStop, TrainRoute


def enumerate_covering_pairs(
    route: TrainRoute, source: str, destination: str
) -> list[tuple[StationStop, StationStop]]:
    """All (board, alight) pairs whose segment fully covers source→destination.

    Booking from an earlier station and/or to a later one is the whole trick:
    those pairs draw on different — often better — quotas. Pairs that do not
    cover the full user leg are never generated.
    """
    codes = [stop.code for stop in route.stations]
    route_str = " → ".join(codes)
    if source not in codes:
        raise InvalidStationError(f"Station {source} is not on this train's route ({route_str})")
    if destination not in codes:
        raise InvalidStationError(
            f"Station {destination} is not on this train's route ({route_str})"
        )
    s, d = codes.index(source), codes.index(destination)
    if s == d:
        raise InvalidStationError("Source and destination are the same station")
    if s > d:
        raise InvalidStationError(
            f"{source} comes after {destination} on this route — check the direction of travel"
        )
    return [
        (route.stations[i], route.stations[j])
        for i in range(s + 1)           # board at the source or any earlier stop
        for j in range(d, len(codes))   # alight at the destination or any later stop
    ]
