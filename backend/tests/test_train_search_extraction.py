"""Pure extraction: a confirmtkt trainList -> list[RawTrainBetween].

Shapes mirror the live confirmtkt /trains/search response (captured 2026-06-16):
both `availabilityCache` (General) and `availabilityCacheTatkal` (Tatkal) carry a
raw `availability` string + `fare` per class; `avlClassesSorted` gives class order.
"""
from app.providers.irctc.provider import build_quota_rows, build_raw_trains_between

_TRAIN = {
    "trainNumber": "12904",
    "trainName": "GOLDEN TEMPLE M",
    "fromStnCode": "NDLS",
    "fromStnName": "New Delhi",
    "toStnCode": "BCT",
    "toStnName": "Mumbai Central",
    "departureTime": "04:00",
    "arrivalTime": "23:55",
    "duration": 1195,
    "runningDays": "1111100",
    "hasPantry": True,
    "distance": "1384",
    "avlClassesSorted": ["3A", "SL"],  # note: 3A before SL
    "availabilityCache": {
        "SL": {"availability": "RLWL3/WL3", "availabilityDisplayName": "WL 3", "fare": "755"},
        "3A": {"availability": "AVAILABLE-0042", "availabilityDisplayName": "AVL 42", "fare": "1980"},
        "ZZ": {"availability": "AVAILABLE-0001", "fare": "10"},  # class our enum doesn't model
    },
    "availabilityCacheTatkal": {
        "SL": {"availability": "NOT AVAILABLE", "availabilityDisplayName": "Not Available", "fare": 0},
    },
}


def test_extracts_single_train_header_fields():
    [t] = build_raw_trains_between([_TRAIN])
    assert t.train_number == "12904"
    assert t.train_name == "GOLDEN TEMPLE M"
    assert (t.from_code, t.from_name) == ("NDLS", "New Delhi")
    assert (t.to_code, t.to_name) == ("BCT", "Mumbai Central")
    assert (t.departure_time, t.arrival_time) == ("04:00", "23:55")
    assert t.duration_min == 1195
    assert t.running_days == "1111100"
    assert t.has_pantry is True
    assert t.distance_km == 1384


def test_general_offers_ordered_by_avl_classes_sorted_and_skip_unknown():
    [t] = build_raw_trains_between([_TRAIN])
    classes = [o.travel_class.value for o in t.general_offers]
    assert classes == ["3A", "SL"]  # avlClassesSorted order; "ZZ" dropped


def test_general_offer_uses_richer_availability_string_and_int_fare():
    [t] = build_raw_trains_between([_TRAIN])
    sl = next(o for o in t.general_offers if o.travel_class.value == "SL")
    assert sl.raw_availability == "RLWL3/WL3"  # not the lossy "WL 3" display
    assert sl.fare == 755


def test_tatkal_offers_extracted_with_raw_fare_zero_unchanged():
    # The 0 -> None business rule is the SERVICE's job; extraction stays faithful.
    [t] = build_raw_trains_between([_TRAIN])
    assert [o.travel_class.value for o in t.tatkal_offers] == ["SL"]
    assert t.tatkal_offers[0].raw_availability == "NOT AVAILABLE"
    assert t.tatkal_offers[0].fare == 0


def test_missing_tatkal_cache_yields_empty_list():
    train = {k: v for k, v in _TRAIN.items() if k != "availabilityCacheTatkal"}
    [t] = build_raw_trains_between([train])
    assert t.tatkal_offers == []


def test_trailing_hash_marker_stripped_for_clean_display():
    # Live confirmtkt decorates some strings with "#"; keep the stored raw clean
    # so status badges don't render "NOT AVAILABLE#".
    train = {
        **_TRAIN,
        "availabilityCache": {"SL": {"availability": "AVAILABLE-0072#", "fare": "840"}},
        "availabilityCacheTatkal": {"SL": {"availability": "NOT AVAILABLE#", "fare": 0}},
        "avlClassesSorted": ["SL"],
    }
    [t] = build_raw_trains_between([train])
    assert t.general_offers[0].raw_availability == "AVAILABLE-0072"
    assert t.tatkal_offers[0].raw_availability == "NOT AVAILABLE"


_QUOTA_TRAIN = {
    "trainNumber": "12904",
    "fromStnCode": "NDLS",
    "departureTime": "04:00",
    "avlClassesSorted": ["3A", "SL"],
    "availabilityCacheForQuota": {
        "SL": {"availability": "RLWL3/WL3", "availabilityDisplayName": "WL 3", "fare": "755"},
        "3A": {"availability": "AVAILABLE-0042", "availabilityDisplayName": "AVL 42", "fare": "1980"},
        "ZZ": {"availability": "AVAILABLE-0001", "fare": "10"},  # class our enum doesn't model
    },
}


def test_build_quota_rows_reads_for_quota_cache_with_disambiguators():
    [(train_number, from_code, departure_time, offers)] = build_quota_rows([_QUOTA_TRAIN])
    assert (train_number, from_code, departure_time) == ("12904", "NDLS", "04:00")
    assert [o.travel_class.value for o in offers] == ["3A", "SL"]  # avlClassesSorted order; ZZ dropped
    sl = next(o for o in offers if o.travel_class.value == "SL")
    assert sl.raw_availability == "RLWL3/WL3"  # richer string, not the lossy "WL 3"
    assert sl.fare == 755


def test_build_quota_rows_empty_cache_yields_no_offers():
    train = {k: v for k, v in _QUOTA_TRAIN.items() if k != "availabilityCacheForQuota"}
    [(_n, _f, _d, offers)] = build_quota_rows([train])
    assert offers == []
