from app.schemas import AvailabilityStatus, ParsedAvailability, Quota


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
