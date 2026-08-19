"""All Pydantic models and enums shared across layers.

Submodules organise by audience (enums, domain, requests, responses,
manifest); this __init__ re-exports everything for backward compatibility.
"""

from app.schemas.domain import (
    Candidate,
    ClassAvailability,
    ParsedAvailability,
    Station,
    StationStop,
    TrainIdentity,
    TrainRoute,
)
from app.schemas.enums import (
    AvailabilityStatus,
    BookingQuota,
    RecommendationNoteCode,
    TravelClass,
)
from app.schemas.manifest import (
    FetchDescriptor,
    FetchResult,
    ManifestResponse,
    ProcessRequest,
)
from app.schemas.requests import (
    RouteManifestRequest,
    SeatFinderManifestRequest,
    TrainSearchManifestRequest,
)
from app.schemas.responses import (
    Recommendation,
    RecommendationResponse,
    SwitchAlternative,
    TrainBetween,
    TrainsBetweenResponse,
    UserLeg,
)

__all__ = [
    # enums
    "AvailabilityStatus",
    "BookingQuota",
    # domain
    "Candidate",
    "ClassAvailability",
    # manifest
    "FetchDescriptor",
    "FetchResult",
    "ManifestResponse",
    "ParsedAvailability",
    "ProcessRequest",
    # responses
    "Recommendation",
    "RecommendationNoteCode",
    "RecommendationResponse",
    # requests
    "RouteManifestRequest",
    "SeatFinderManifestRequest",
    "Station",
    "StationStop",
    "SwitchAlternative",
    "TrainBetween",
    "TrainIdentity",
    "TrainRoute",
    "TrainSearchManifestRequest",
    "TrainsBetweenResponse",
    "TravelClass",
    "UserLeg",
]
