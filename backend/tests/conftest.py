"""Shared fixtures. Tests need a Redis they may wipe: set REDIS_URL to a throwaway
instance (CI runs one as a service container)."""

import datetime as dt
import json
import os
from urllib.parse import parse_qs, urlparse

import pytest

if not os.environ.get("REDIS_URL"):
    # The app's default is a real local Redis; never flush that by accident.
    pytest.exit("Set REDIS_URL to a disposable Redis (the tests flush it)", returncode=2)

from app.infrastructure.cache import RouteCache
from app.infrastructure.manifest_store import ManifestCache
from app.infrastructure.redis import close_redis, get_redis
from app.schemas import (
    BookingQuota,
    FetchResult,
    ManifestResponse,
    StationStop,
    TrainRoute,
    TravelClass,
)
from app.services import seat_finder


@pytest.fixture(autouse=True)
async def redis():
    # pytest-asyncio gives each test its own event loop; the shared Redis pool is
    # bound to the loop that created it, so start and end every test without one.
    await close_redis()
    r = get_redis()
    await r.flushdb()
    ManifestCache._store.clear()
    yield r
    await r.flushdb()
    await close_redis()


def route_of(train: str, stops: list[tuple[str, int, int]]) -> TrainRoute:
    """stops: (code, distance_km, day_offset)"""
    return TrainRoute(
        train_number=train,
        train_name="TEST EXP",
        stations=[
            StationStop(code=c, name=c, distance_km=km, day_offset=day)
            for c, km, day in stops
        ],
    )


def fmt(d: dt.date) -> str:
    return d.strftime("%d-%m-%Y")


def avl_entry(availability: str | None, fare: str = "300", prediction: int = 90) -> dict:
    return {
        "availability": availability,
        "availabilityDisplayName": availability or "",
        "fare": fare,
        "predictionPercentage": prediction,
    }


def train_dict(
    train: str,
    board: str,
    alight: str,
    sl: str | None,
    departure: str = "10:00",
    duration: int = 60,
) -> dict:
    """A confirmtkt trainList entry as the frontend forwards it (SL + 3A, General)."""
    return {
        "trainNumber": train,
        "fromStnCode": board,
        "toStnCode": alight,
        "departureTime": departure,
        "duration": duration,
        "availabilityCache": {
            "SL": avl_entry(sl),
            "3A": avl_entry("AVAILABLE-0010", fare="800", prediction=100),
        },
        "availabilityCacheTatkal": {},
        "availabilityCacheForQuota": {},
    }


class FakeConfirmtkt:
    """Answers confirmtkt search descriptors from a 'true' timetable, which may
    disagree with the route's (erail) day offsets.

    dep/arr: absolute minutes from midnight of the origin date.
    runs: origin dates the train runs on (None = daily).
    """

    def __init__(
        self,
        train,
        dep,
        arr,
        runs=None,
        unsold=(),
        substitute=None,
        fail=(),
        blackout=(),
    ):
        self.train, self.dep, self.arr, self.runs = train, dep, arr, runs
        self.unsold, self.fail, self.blackout = set(unsold), set(fail), set(blackout)
        self.substitute = substitute or {}
        self.calls: list[tuple[str, str, dt.date]] = []

    def origin_for(self, board: str, date: dt.date) -> dt.date | None:
        origin = date - dt.timedelta(days=self.dep[board] // 1440)
        return origin if self.runs is None or origin in self.runs else None

    @staticmethod
    def availability_for(origin: dt.date) -> str:
        # differs per run, so data from the wrong day's run is detectable
        return f"AVAILABLE-{(origin.toordinal() % 50) + 1:04d}"

    def respond(self, url: str, fetch_id: str) -> FetchResult:
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        board, alight = q["sourceStationCode"], q["destinationStationCode"]
        date = dt.datetime.strptime(q["dateOfJourney"], "%d-%m-%Y").date()
        self.calls.append((board, alight, date))
        if (board, alight) in self.fail:
            return FetchResult(fetch_id=fetch_id, status=429, body="")
        listed = []
        origin = self.origin_for(board, date)
        if (
            origin is not None
            and board not in self.unsold
            and alight not in self.unsold
            and (board, date) not in self.blackout
        ):
            dep = self.dep[board]
            listed.append(
                train_dict(
                    self.train,
                    self.substitute.get(board, board),
                    alight,
                    self.availability_for(origin),
                    departure=f"{dep % 1440 // 60:02d}:{dep % 60:02d}",
                    duration=self.arr[alight] - dep,
                )
            )
        # what the frontend posts: trainList pre-filtered to the target train
        body = json.dumps({"data": {"trainList": listed}})
        return FetchResult(fetch_id=fetch_id, status=200, body=body)


async def run_search(
    fake: FakeConfirmtkt,
    route: TrainRoute,
    source: str,
    destination: str,
    date: dt.date,
    travel_class: TravelClass = TravelClass.SL,
):
    """Drive the seat-finder manifest loop like the frontend does."""
    await RouteCache.put(route.train_number, route)
    resp = await seat_finder.create_manifest(
        route.train_number,
        source,
        destination,
        date,
        travel_class,
        BookingQuota.GENERAL,
        False,
        1.0,
        True,
    )
    rounds = 0
    while isinstance(resp, ManifestResponse):
        rounds += 1
        results = [
            FetchResult(fetch_id=f.fetch_id, status=200, body="")  # no live override
            if f.fetch_id.startswith("verify:")
            else fake.respond(f.url, f.fetch_id)
            for f in resp.fetches
        ]
        resp = await seat_finder.process_manifest(resp.manifest_id, results)
    return resp, rounds


def picks(resp) -> dict[tuple[str, str], object]:
    return {(r.book_from, r.book_to): r for r in resp.recommendations}
