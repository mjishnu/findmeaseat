"""The seam between the app and its data source."""
import datetime as dt
from typing import Protocol

from app.schemas import BookingQuota, RawClassOffer, RawTrainBetween, TrainRoute, TravelClass


class RailDataProvider(Protocol):
    """Interface every data source must satisfy.

    Methods are async so a provider can fan out concurrent HTTP calls.
    providers/irctc implements this against erail.in + confirmtkt (the only
    runtime data source). To add another source — a different scraper, an
    official API, a DB — implement this Protocol in a sibling package and return
    it from app.dependencies.get_provider.

    get_seat_status returns a RAW availability string (e.g. "AVAILABLE-0042",
    "GNWL50/WL30"); app.core.parser.parse_availability normalizes it, so every
    real-world format passes straight through without provider-side parsing.

    The optional `quota` selects which confirmtkt cache a method reads. GN and TQ
    are bundled in one response (reading the other costs no extra call); LD and SS
    each need a separate quota=-parameterised fetch. It defaults to GENERAL, so
    every existing call site behaves identically.
    """

    async def get_route(self, train_number: str) -> TrainRoute | None: ...

    async def get_seat_status(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> str: ...

    async def get_fare(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        travel_class: TravelClass,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> int | None: ...  # None when the class isn't priced/offered on this leg

    async def get_class_options(
        self,
        train_number: str,
        source: str,
        destination: str,
        journey_date: dt.date,
        quota: BookingQuota = BookingQuota.GENERAL,
    ) -> list[tuple[str, str, int | None]]: ...
    # (class_code, RAW availability string, fare) for every class the train
    # offers on this leg in `quota` — used to suggest a better class/quota. Reuses
    # the same upstream response as get_seat_status, so it costs no extra request.

    async def search_trains_between(
        self,
        source: str,
        destination: str,
        journey_date: dt.date,
    ) -> list[RawTrainBetween]: ...
    # Every train running source→destination on the date, each with RAW per-class
    # availability for BOTH General and Tatkal quotas. The service normalizes the
    # raw strings (parser + ranking) into the public TrainsBetweenResponse.

    async def search_quota_availability(
        self,
        source: str,
        destination: str,
        journey_date: dt.date,
        quota: BookingQuota,
    ) -> list[tuple[str, str, str, list[RawClassOffer]]]: ...
    # Per-train (train_number, from_code, departure_time, RAW per-class offers) for one
    # quota (LD/SS), read from confirmtkt's availabilityCacheForQuota. The service
    # normalizes the raw strings into TrainsQuotaAvailabilityResponse.
