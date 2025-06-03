from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict


class KillRequest(BaseModel):
    """Request body for job termination."""

    job_id: str


class RequeueRequest(BaseModel):
    """Request body for job requeueing."""

    job_id: str


class MetricsResponse(BaseModel):
    """Response model containing a list of metrics."""

    metrics: List[Dict[str, Any]]


class JobModel(BaseModel):
    """Representation of a job record."""

    model_config = ConfigDict(extra="allow")
    id: str
    status: str
    retry_index: int | None = None


class ConfigResponse(BaseModel):
    """Response model wrapping a configuration dictionary."""

    model_config = ConfigDict(extra="allow")
    config: Dict[str, Any]
