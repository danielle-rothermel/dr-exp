from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict


class KillRequest(BaseModel):
    """Request body for job termination."""

    job_id: str


class RequeueRequest(BaseModel):
    """Request body for job requeueing."""

    job_id: str


class BoostPriorityRequest(BaseModel):
    """Request body for boosting job priority."""

    job_id: str
    boost_amount: int = 100


class SetPriorityRequest(BaseModel):
    """Request body for setting job priority."""

    job_id: str
    priority: int
    reason: str | None = None


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


class PriorityResponse(BaseModel):
    """Response model for priority operations."""

    job_id: str
    old_priority: int
    new_priority: int
    success: bool
    message: str


class ErrorResponse(BaseModel):
    """Standardized error response model."""

    error: str
    detail: str
    job_id: str | None = None


class SuccessResponse(BaseModel):
    """Standardized success response model."""

    success: bool = True
    message: str
    job_id: str | None = None
