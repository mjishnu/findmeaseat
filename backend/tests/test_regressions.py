"""Regression tests for bugs found in the 2026-10 audit."""

import datetime as dt
import json

import httpx
import msgpack
import pytest
import zstandard as zstd
from conftest import route_of, train_dict

from app.domain import dates
from app.domain.ranking import sort_candidates
from app.exceptions import InvalidJourneyDateError
from app.infrastructure.cache import RouteCache, TrainSearchCache
from app.main import app
from app.providers.prefetched.client import format_date
from app.schemas import (
    AvailabilityStatus,
    BookingQuota,
    Candidate,
    FetchResult,
    ManifestResponse,
    ParsedAvailability,
    RecommendationNoteCode,
    StationStop,
    TravelClass,
)
from app.services import seat_finder, train_search
from app.services.recommendations import build_verified_response
from app.services.recommendations.evaluator import (
    build_better_alternatives,
    build_recommendation,
)

W, R, A, N = (
    AvailabilityStatus.WAITLIST,
    AvailabilityStatus.RAC,
    AvailabilityStatus.AVAILABLE,
    AvailabilityStatus.NOT_BOOKABLE,
)


def stop(code, km=0, day=0):
    return StationStop(code=code, name=code, distance_km=km, day_offset=day)


def parsed(raw, status):
    return ParsedAvailability(raw=raw, status=status)


def cand(board, alight, raw, status, p=0.9, cov=1.0, board_at="", alight_at=""):
    return Candidate(
        board=stop(board), alight=stop(alight, 100), parsed=parsed(raw, status),
        probability=p, extra_km=0, fare=500, extra_fare=0, coverage_pct=cov,
        board_at=board_at, alight_at=alight_at,
    )


# ── booking window counts from the train's origin date ──────────────────────

def test_arp_extends_for_stations_later_in_the_run():
    today = dates.booking_day_today()
    dates.validate_journey_date(today + dt.timedelta(days=61), extra_days=1)
    with pytest.raises(InvalidJourneyDateError):
        dates.validate_journey_date(today + dt.timedelta(days=61))
    with pytest.raises(InvalidJourneyDateError):
        dates.validate_journey_date(today - dt.timedelta(days=1), extra_days=3)


async def test_seat_finder_accepts_day_two_station_past_60_days():
    route = route_of("12617", [("ERS", 0, 0), ("MAO", 900, 1), ("BPL", 1800, 2)])
    await RouteCache.put("12617", route)
    today = dates.booking_day_today()
    m = await seat_finder.create_manifest(
        "12617", "MAO", "BPL", today + dt.timedelta(days=61),
        TravelClass.SL, BookingQuota.GENERAL, False, 1.0, True,
    )
    assert isinstance(m, ManifestResponse)
    with pytest.raises(InvalidJourneyDateError):
        await seat_finder.create_manifest(
            "12617", "ERS", "BPL", today + dt.timedelta(days=61),
            TravelClass.SL, BookingQuota.GENERAL, False, 1.0, True,
        )


async def test_search_spanning_ist_midnight_completes(monkeypatch):
    route = route_of("12617", [("ERS", 0, 0), ("MAO", 900, 1), ("BPL", 1800, 2)])
    await RouteCache.put("12617", route)
    today = dates.booking_day_today()
    m = await seat_finder.create_manifest(
        "12617", "MAO", "BPL", today, TravelClass.SL, BookingQuota.GENERAL, False, 1.0, True
    )
    monkeypatch.setattr(dates, "booking_day_today", lambda: today + dt.timedelta(days=1))
    await seat_finder.process_manifest(
        m.manifest_id, [FetchResult(fetch_id=f.fetch_id, status=200, body="") for f in m.fetches]
    )


# ── live verify ─────────────────────────────────────────────────────────────

def _ranked(*boards):
    today = dates.booking_day_today()
    ctx = {
        "train_number": "1", "train_name": "T", "journey_date": today.isoformat(),
        "travel_class": "SL", "quota": "GN",
        "user_leg": {"source": "B", "destination": "D", "distance_km": 100, "fare": 500, "availability": None},
        "pairs_evaluated": len(boards), "pairs_skipped": 0,
    }
    cands = [
        {
            "board": stop(b).model_dump(), "alight": stop("D", 100).model_dump(),
            "parsed": parsed(f"WL {i + 3}", W).model_dump(), "probability": 0.9,
            "extra_km": 0, "fare": 500, "extra_fare": 0, "coverage_pct": 1.0,
            "board_at": "B", "alight_at": "D",
        }
        for i, b in enumerate(boards)
    ]
    return {"candidates": cands, "alternatives": [], "context": ctx}


@pytest.mark.parametrize("live", ["TRAIN DEPARTED", "REGRET"])
def test_live_check_drops_unbookable_picks(live):
    resp = build_verified_response(
        _ranked("B", "A"), {"B|D": {"availability": parsed(live, N), "fare": 500}}
    )
    assert [r.book_from for r in resp.recommendations] == ["A"]


def test_live_answer_without_fare_keeps_known_fare():
    resp = build_verified_response(
        _ranked("B"), {"B|D": {"availability": parsed("WL 2", W), "fare": None, "prediction_pct": 90}}
    )
    assert resp.recommendations[0].fare == 500


# ── ranking ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "worse, better, status, p",
    [("RAC 48", "RAC 2", R, 0.95), ("WL 48", "WL 2", W, 0.5), ("AVL 2", "AVL 48", A, 0.99)],
)
def test_queue_position_tie_break(worse, better, status, p):
    _, best, _ = sort_candidates(
        [cand("X", "D", worse, status, p), cand("Y", "D", better, status, p)], 500, 100
    )
    assert best.parsed.raw == better


# ── recommendation notes describe the ticket actually booked ────────────────

def test_partial_pair_notes():
    notes = build_recommendation(
        1, cand("BDJ", "KGQ", "AVL 5", A, cov=0.6, board_at="BDJ", alight_at="KGQ"), "CLT", "CAN"
    ).notes
    assert RecommendationNoteCode.BOARDING_CHANGE not in notes
    assert RecommendationNoteCode.ALIGHT_CHANGE not in notes
    assert RecommendationNoteCode.PARTIAL_COVERAGE in notes


def test_covering_pair_notes():
    notes = build_recommendation(
        1, cand("TVC", "BPL", "AVL 5", A, board_at="CLT", alight_at="CAN"), "CLT", "CAN"
    ).notes
    assert RecommendationNoteCode.BOARDING_CHANGE in notes
    assert RecommendationNoteCode.ALIGHT_CHANGE in notes


async def test_fare_delta_unknown_when_a_fare_is_unknown():
    class Provider:
        async def get_train_classes(self, *a, **k):
            return [TravelClass.AC3]

        async def get_fare(self, s, d, tc, q=None):
            return 900 if tc == TravelClass.AC3 else -1

        async def get_seat_status(self, s, d, tc, q=None):
            return parsed("AVL 9", A) if tc == TravelClass.AC3 else parsed("WL 9", W)

        async def get_seat_prediction(self, *a, **k):
            return 50

    alts = await build_better_alternatives(
        Provider(), [(stop("B"), stop("D", 100))], "B", "D", {"B": 0, "D": 100}, 100,
        TravelClass.SL, BookingQuota.GENERAL, None, -1,
    )
    assert alts and alts[0].fare_delta is None


# ── trains-between never caches confirmtkt placeholders ─────────────────────

@pytest.mark.parametrize("availability, cached", [(None, False), ("AVAILABLE-0010", True)])
async def test_trains_between_caches_only_real_availability(availability, cached):
    date = dates.booking_day_today() + dt.timedelta(days=10)
    m = await train_search.get_or_create_manifest("PAZ", "GWL", date, BookingQuota.GENERAL)
    t = train_dict("12617", "PAZ", "GWL", availability)
    t["availabilityCache"] = {"SL": t["availabilityCache"]["SL"]}  # SL only
    body = json.dumps({"data": {"trainList": [t]}})
    await train_search.process_manifest(m.manifest_id, [FetchResult(fetch_id="search", status=200, body=body)])
    assert bool(await TrainSearchCache.get_all("PAZ", "GWL", format_date(date), None)) is cached


# ── "no data yet" is reported apart from "unavailable" ──────────────────────

async def test_placeholder_only_search_reports_no_data():
    route = route_of("12617", [("ERS", 0, 0), ("MAO", 900, 0), ("BPL", 1800, 0)])
    await RouteCache.put("12617", route)
    m = await seat_finder.create_manifest(
        "12617", "ERS", "BPL", dates.booking_day_today() + dt.timedelta(days=5),
        TravelClass.SL, BookingQuota.GENERAL, False, 1.0, True,
    )

    def placeholder(fetch_id):
        board, alight, _ = fetch_id.split("|")
        t = train_dict("12617", board, alight, None)
        t["availabilityCache"] = {"SL": t["availabilityCache"]["SL"]}
        return json.dumps({"data": {"trainList": [t]}})

    res = await seat_finder.process_manifest(
        m.manifest_id,
        [FetchResult(fetch_id=f.fetch_id, status=200, body=placeholder(f.fetch_id)) for f in m.fetches],
    )
    while isinstance(res, ManifestResponse):  # live checks fail too
        res = await seat_finder.process_manifest(
            res.manifest_id, [FetchResult(fetch_id=f.fetch_id, status=0, body="") for f in res.fetches]
        )
    assert res.pairs_no_data == res.pairs_evaluated
    assert res.recommendations == []


# ── zstd bodies can't inflate past the cap ──────────────────────────────────

def _zstd_frame(size: int, declare_size: bool = True) -> bytes:
    cctx = zstd.ZstdCompressor(level=3, write_content_size=declare_size)
    cobj = cctx.compressobj(size=size if declare_size else -1)
    chunk = b"1" * (1 << 20)
    out = [cobj.compress(chunk) for _ in range(size // len(chunk))]
    return b"".join(out) + cobj.flush()


@pytest.mark.parametrize("declare_size", [True, False])
async def test_zstd_bomb_rejected_before_decompressing(declare_size):
    bomb = _zstd_frame(64 << 20, declare_size)
    assert len(bomb) < 64 << 10
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(
            "/api/route/manifest",
            content=bomb,
            headers={"Content-Type": "application/x-msgpack", "Content-Encoding": "zstd"},
        )
    assert r.status_code == 413


async def test_normal_zstd_msgpack_request_still_works():
    body = zstd.ZstdCompressor(level=3).compress(msgpack.packb({"train_number": "12617"}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(
            "/api/route/manifest",
            content=body,
            headers={"Content-Type": "application/x-msgpack", "Content-Encoding": "zstd"},
        )
    assert r.status_code == 200
