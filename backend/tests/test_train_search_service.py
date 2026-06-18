"""TrainSearchService: normalize raw provider offers into the public response."""
import datetime as dt

import pytest

from app.core.dates import booking_day_today
from app.core.ranking import confirmation_probability
from app.exceptions import InvalidJourneyDateError
from app.schemas import AvailabilityStatus, BookingQuota, RawClassOffer, RawTrainBetween, TravelClass
from app.services.train_search import TrainSearchService


def _raw(general: list[RawClassOffer], tatkal: list[RawClassOffer]) -> RawTrainBetween:
    return RawTrainBetween(
        train_number="12904",
        train_name="GOLDEN TEMPLE M",
        from_code="NDLS",
        from_name="New Delhi",
        to_code="BCT",
        to_name="Mumbai Central",
        departure_time="04:00",
        arrival_time="23:55",
        duration_min=1195,
        running_days="1111100",
        has_pantry=True,
        distance_km=1384,
        general_offers=general,
        tatkal_offers=tatkal,
    )


class _FakeProvider:
    def __init__(self, trains: list[RawTrainBetween]):
        self._trains = trains
        self.calls: list[tuple] = []

    async def search_trains_between(self, source, destination, journey_date):
        self.calls.append((source, destination, journey_date))
        return self._trains


def _tomorrow() -> dt.date:
    return booking_day_today() + dt.timedelta(days=1)


async def test_normalizes_general_offers_in_order():
    provider = _FakeProvider([_raw(
        general=[
            RawClassOffer(travel_class=TravelClass.AC3, raw_availability="AVAILABLE-0042", fare=1980),
            RawClassOffer(travel_class=TravelClass.SL, raw_availability="RLWL3/WL3", fare=755),
        ],
        tatkal=[],
    )])
    res = await TrainSearchService(provider).search("ndls", "bct", _tomorrow())
    [train] = res.trains
    assert [c.travel_class.value for c in train.general] == ["3A", "SL"]
    avail3a = train.general[0]
    assert avail3a.availability.status is AvailabilityStatus.AVAILABLE
    assert avail3a.probability == confirmation_probability(avail3a.availability)
    assert avail3a.fare == 1980
    sl = train.general[1]
    assert sl.availability.status is AvailabilityStatus.WAITLIST


async def test_tatkal_not_available_fare_zero_becomes_none():
    provider = _FakeProvider([_raw(
        general=[RawClassOffer(travel_class=TravelClass.SL, raw_availability="AVAILABLE-0010", fare=755)],
        tatkal=[RawClassOffer(travel_class=TravelClass.SL, raw_availability="NOT AVAILABLE", fare=0)],
    )])
    res = await TrainSearchService(provider).search("NDLS", "BCT", _tomorrow())
    tatkal_sl = res.trains[0].tatkal[0]
    assert tatkal_sl.fare is None
    assert tatkal_sl.availability.status is AvailabilityStatus.NOT_BOOKABLE


async def test_empty_tatkal_list_stays_empty():
    provider = _FakeProvider([_raw(
        general=[RawClassOffer(travel_class=TravelClass.SL, raw_availability="AVAILABLE-0010", fare=755)],
        tatkal=[],
    )])
    res = await TrainSearchService(provider).search("NDLS", "BCT", _tomorrow())
    assert res.trains[0].tatkal == []


async def test_no_trains_returns_empty_list_not_error():
    res = await TrainSearchService(_FakeProvider([])).search("NDLS", "BCT", _tomorrow())
    assert res.trains == []


async def test_source_destination_uppercased_and_echoed():
    provider = _FakeProvider([])
    res = await TrainSearchService(provider).search("ndls", "bct", _tomorrow())
    assert (res.source, res.destination) == ("NDLS", "BCT")
    assert provider.calls == [("NDLS", "BCT", _tomorrow())]
    assert res.journey_date == _tomorrow()


async def test_past_date_rejected():
    provider = _FakeProvider([])
    with pytest.raises(InvalidJourneyDateError):
        await TrainSearchService(provider).search(
            "NDLS", "BCT", booking_day_today() - dt.timedelta(days=1)
        )


class _QuotaProvider:
    def __init__(self, rows):
        self._rows = rows
        self.calls: list[tuple] = []

    async def search_quota_availability(self, source, destination, journey_date, quota):
        self.calls.append((source, destination, journey_date, quota))
        return self._rows


async def test_search_quota_normalizes_rows_with_disambiguators():
    rows = [("12904", "NDLS", "04:00", [
        RawClassOffer(travel_class=TravelClass.AC3, raw_availability="AVAILABLE-0042", fare=1980),
        RawClassOffer(travel_class=TravelClass.SL, raw_availability="NOT AVAILABLE", fare=0),
    ])]
    provider = _QuotaProvider(rows)
    res = await TrainSearchService(provider).search_quota("ndls", "bct", _tomorrow(), BookingQuota.LADIES)
    assert (res.source, res.destination, res.quota) == ("NDLS", "BCT", BookingQuota.LADIES)
    [train] = res.trains
    assert (train.train_number, train.from_code, train.departure_time) == ("12904", "NDLS", "04:00")
    assert [c.travel_class.value for c in train.classes] == ["3A", "SL"]
    assert train.classes[0].availability.status is AvailabilityStatus.AVAILABLE
    sl = train.classes[1]
    assert sl.availability.status is AvailabilityStatus.NOT_BOOKABLE
    assert sl.fare is None  # 0 -> None business rule
    assert provider.calls == [("NDLS", "BCT", _tomorrow(), BookingQuota.LADIES)]
