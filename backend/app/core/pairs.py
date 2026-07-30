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
