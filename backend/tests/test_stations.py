from app.schemas import Station
from app.services.stations import search_stations


def test_search_stations_exact_and_fuzzy():
    res = search_stations("CSMT")
    assert len(res) >= 1
    assert res[0].code == "CSMT"

    res_prefix = search_stations("NDLS")
    assert len(res_prefix) >= 1
    assert res_prefix[0].code == "NDLS"

    res_empty = search_stations("  ")
    assert len(res_empty) == 0
