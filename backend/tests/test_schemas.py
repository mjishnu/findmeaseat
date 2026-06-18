from app.schemas import (
    AvailabilityStatus,
    ClassAvailability,
    ParsedAvailability,
    Quota,
    RawClassOffer,
    TravelClass,
)


def test_raw_class_offer_carries_optional_prediction():
    o = RawClassOffer(travel_class=TravelClass.SL, raw_availability="GNWL5/WL3")
    assert o.prediction_pct is None
    o2 = RawClassOffer(travel_class=TravelClass.SL, raw_availability="GNWL5/WL3", prediction_pct=0)
    assert o2.prediction_pct == 0


def test_class_availability_probability_accepts_none():
    parsed = ParsedAvailability(raw="GNWL5/WL3", status=AvailabilityStatus.WAITLIST)
    ca = ClassAvailability(travel_class=TravelClass.SL, availability=parsed, probability=None)
    assert ca.probability is None


def test_waitlist_label_shows_quota_and_current_position():
    parsed = ParsedAvailability(
        raw="GNWL15/WL10",
        status=AvailabilityStatus.WAITLIST,
        quota=Quota.GNWL,
        series_wl=15,
        current_wl=10,
    )
    assert parsed.label == "GNWL 10"


def test_available_label_includes_seat_count_when_known():
    with_seats = ParsedAvailability(
        raw="AVAILABLE-0044", status=AvailabilityStatus.AVAILABLE, seats=44
    )
    without = ParsedAvailability(raw="WL3/AVAILABLE", status=AvailabilityStatus.AVAILABLE)
    assert with_seats.label == "AVAILABLE (44 seats)"
    assert without.label == "AVAILABLE"


def test_rac_label():
    parsed = ParsedAvailability(
        raw="RAC 12/RAC 5", status=AvailabilityStatus.RAC, series_wl=12, current_wl=5
    )
    assert parsed.label == "RAC 5"
