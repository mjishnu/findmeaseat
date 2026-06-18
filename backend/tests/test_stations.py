"""StationDirectory: in-memory ranked station lookup for autocomplete."""
from app.schemas import Station
from app.services.stations import StationDirectory

_STATIONS = [
    Station(code="NDLS", name="New Delhi", city="New Delhi"),
    Station(code="NZM", name="Delhi Hazrat Nizamuddin", city="Delhi"),
    Station(code="DLI", name="Old Delhi", city="Delhi"),
    Station(code="BCT", name="Mumbai Central", city="Mumbai"),
    Station(code="CSTM", name="Mumbai Csmt", city="Mumbai"),
    Station(code="ADH", name="Andheri", city="Mumbai"),
]


def _dir() -> StationDirectory:
    return StationDirectory(_STATIONS)


def test_exact_code_match_ranks_first():
    results = _dir().search("ndls")
    assert results[0].code == "NDLS"


def test_search_is_case_insensitive():
    assert _dir().search("NDLS") == _dir().search("ndls")


def test_name_prefix_excludes_unrelated_stations():
    codes = {s.code for s in _dir().search("mum")}
    assert "NDLS" not in codes
    assert {"BCT", "CSTM"} <= codes


def test_name_match_ranks_above_city_only_match():
    # "Mumbai Central"/"Mumbai Csmt" (name prefix) must outrank "Andheri",
    # which only matches because its city is Mumbai.
    results = _dir().search("mumbai")
    codes = [s.code for s in results]
    assert codes.index("BCT") < codes.index("ADH")
    assert codes.index("CSTM") < codes.index("ADH")


def test_substring_match_on_name_or_city():
    codes = {s.code for s in _dir().search("delhi")}
    # New Delhi (name), Delhi Hazrat Nizamuddin (name/city), Old Delhi (name)
    assert {"NDLS", "NZM", "DLI"} <= codes


def test_limit_caps_result_count():
    assert len(_dir().search("a", limit=2)) <= 2


def test_no_match_returns_empty():
    assert _dir().search("zzzzz") == []


def test_blank_query_returns_empty():
    assert _dir().search("   ") == []
