"""Manifest-protocol schemas (fetch descriptor / process results)."""

from pydantic import BaseModel, Field


class FetchDescriptor(BaseModel):
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    fetch_id: str
    method: str = "GET"
    body: str | None = None


class ManifestResponse(BaseModel):
    manifest_id: str
    fetches: list[FetchDescriptor]


class FetchResult(BaseModel):
    fetch_id: str
    status: int
    body: str


class ProcessRequest(BaseModel):
    manifest_id: str
    results: list[FetchResult]
