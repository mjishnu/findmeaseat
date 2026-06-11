import pytest

from app.core.pairs import enumerate_covering_pairs
from app.exceptions import InvalidStationError
from app.providers.mock.fixtures import DEMO_TRAIN


def test_c_to_d_yields_all_nine_covering_pairs():
    pairs = enumerate_covering_pairs(DEMO_TRAIN, "C", "D")
    legs = {(b.code, a.code) for b, a in pairs}
    assert legs == {
        ("A", "D"), ("A", "E"), ("A", "F"),
        ("B", "D"), ("B", "E"), ("B", "F"),
        ("C", "D"), ("C", "E"), ("C", "F"),
    }


def test_every_pair_fully_covers_the_user_leg():
    codes = [s.code for s in DEMO_TRAIN.stations]
    for board, alight in enumerate_covering_pairs(DEMO_TRAIN, "B", "E"):
        assert codes.index(board.code) <= codes.index("B")
        assert codes.index(alight.code) >= codes.index("E")


def test_full_route_journey_yields_single_pair():
    pairs = enumerate_covering_pairs(DEMO_TRAIN, "A", "F")
    assert [(b.code, a.code) for b, a in pairs] == [("A", "F")]


def test_unknown_station_rejected():
    with pytest.raises(InvalidStationError, match="not on this train's route"):
        enumerate_covering_pairs(DEMO_TRAIN, "Z", "D")


def test_wrong_direction_rejected():
    with pytest.raises(InvalidStationError, match="comes after"):
        enumerate_covering_pairs(DEMO_TRAIN, "D", "C")


def test_same_station_rejected():
    with pytest.raises(InvalidStationError, match="same station"):
        enumerate_covering_pairs(DEMO_TRAIN, "C", "C")
