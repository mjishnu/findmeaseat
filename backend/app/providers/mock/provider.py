"""Deterministic fake RailDataProvider.

Seeding random.Random with the full query string makes results look random
across pairs/dates but identical for repeated calls (CPython seeds str via
SHA-512, stable across processes) — so tests and re-searches are stable.
"""
import datetime as dt
import random

from app.providers.mock.fixtures import REMOTE_LOCATIONS, TRAINS, calculate_fare
from app.schemas import TrainRoute


class MockRailDataProvider:
    def get_route(self, train_number: str) -> TrainRoute | None:
        return TRAINS.get(train_number)

    def get_fare(self, train_number: str, source: str, destination: str) -> int:
        km = {s.code: s.distance_km for s in TRAINS[train_number].stations}
        return calculate_fare(abs(km[destination] - km[source]))

    def get_seat_status(
        self, train_number: str, source: str, destination: str, journey_date: dt.date
    ) -> str:
        # Assumes the service validated train/stations first.
        codes = [s.code for s in TRAINS[train_number].stations]
        i, j = codes.index(source), codes.index(destination)
        rng = random.Random(f"{train_number}|{source}|{destination}|{journey_date.isoformat()}")

        # Quota mirrors real IRCTC mechanics: the origin controls the big
        # general quota; pairs touching a remote location or the terminus
        # draw RLWL; everything else shares the small pooled quota.
        if i == 0:
            quota, p_available = "GNWL", 0.40
        elif j == len(codes) - 1 or source in REMOTE_LOCATIONS or destination in REMOTE_LOCATIONS:
            quota, p_available = "RLWL", 0.15
        else:
            quota, p_available = "PQWL", 0.10

        roll = rng.random()
        if roll < 0.08:
            return "REGRET"
        if roll < 0.08 + p_available:
            seats = rng.randint(1, 60)
            # Emit both real-world formats so the parser's normalization is exercised.
            return rng.choice([f"AVAILABLE-{seats:04d}", f"AVAILABLE {seats}"])
        series = rng.randint(2, 40)
        current = rng.randint(1, series)
        return rng.choice([f"{quota}{series}/WL{current}", f"{quota} {series}/WL {current}"])
