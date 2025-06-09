from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class KillRequest(BaseModel):
    """Request body for job termination."""

    job_id: str = Field(..., description="Job identifier to terminate")


class RequeueRequest(BaseModel):
    """Request body for job requeueing."""

    job_id: str = Field(..., description="Job identifier to requeue")


class BoostPriorityRequest(BaseModel):
    """Request body for boosting job priority."""

    job_id: str = Field(..., description="Job identifier to boost")
    boost_amount: int = Field(
        100, ge=1, le=1000, description="Amount to boost priority"
    )


class SetPriorityRequest(BaseModel):
    """Request body for setting job priority."""

    job_id: str = Field(..., description="Job identifier to update")
    priority: int = Field(..., ge=0, le=1000, description="New priority value (0-1000)")
    reason: Optional[str] = Field(
        None, description="Optional reason for priority change"
    )


class MetricsResponse(BaseModel):
    """Response model containing a list of metrics."""

    metrics: List[Dict[str, Any]] = Field(..., description="List of metric records")
    count: int = Field(..., description="Number of metrics returned")

    def __init__(self, **data: Any) -> None:
        if "metrics" in data and "count" not in data:
            data["count"] = len(data["metrics"])
        super().__init__(**data)


class JobModel(BaseModel):
    """Representation of a job record."""

    id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Current job status")
    priority: int = Field(100, ge=0, le=1000, description="Job priority (0-1000)")
    retry_index: int = Field(0, ge=0, description="Number of retry attempts")
    assigned_worker: Optional[str] = Field(
        None, description="Worker assigned to this job"
    )
    created_at: str = Field(..., description="Job creation timestamp")
    started_at: Optional[str] = Field(None, description="Job start timestamp")
    end_time: Optional[str] = Field(None, description="Job completion timestamp")
    heartbeat: Optional[str] = Field(None, description="Last worker heartbeat")
    kill_requested: Optional[bool] = Field(
        False, description="Whether job termination was requested"
    )
    config_id: Optional[str] = Field(None, description="Configuration identifier")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid_statuses = {"queued", "running", "completed", "failed", "killed"}
        if v not in valid_statuses:
            raise ValueError(f"Status must be one of: {valid_statuses}")
        return v


class ConfigResponse(BaseModel):
    """Response model wrapping a configuration dictionary."""

    config: Dict[str, Any] = Field(..., description="Job configuration dictionary")


class PriorityResponse(BaseModel):
    """Response model for priority operations."""

    job_id: str = Field(..., description="Job identifier")
    old_priority: int = Field(..., ge=0, le=1000, description="Previous priority value")
    new_priority: int = Field(..., ge=0, le=1000, description="New priority value")
    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Human-readable operation result")


class ErrorResponse(BaseModel):
    """Standardized error response model."""

    error: str = Field(..., description="Error type or category")
    detail: str = Field(..., description="Detailed error message")
    job_id: Optional[str] = Field(
        None, description="Related job identifier if applicable"
    )


class SuccessResponse(BaseModel):
    """Standardized success response model."""

    success: bool = Field(True, description="Operation success indicator")
    message: str = Field(..., description="Human-readable success message")
    job_id: Optional[str] = Field(
        None, description="Related job identifier if applicable"
    )


class PaginatedJobsResponse(BaseModel):
    """Paginated response for job listings."""

    jobs: List[JobModel] = Field(..., description="List of jobs for current page")
    total: int = Field(..., ge=0, description="Total number of jobs")
    page: int = Field(..., ge=1, description="Current page number")
    per_page: int = Field(..., ge=1, le=100, description="Number of jobs per page")
    pages: int = Field(..., ge=0, description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")


class HealthResponse(BaseModel):
    """API health check response."""

    status: str = Field(..., description="Health status (healthy/unhealthy)")
    timestamp: str = Field(..., description="Current timestamp")
    uptime_seconds: float = Field(..., description="API uptime in seconds")
    version: str = Field(..., description="API version")
    database_status: str = Field(..., description="Database connection status")
    job_stats: Dict[str, int] = Field(
        ..., description="Current job statistics by status"
    )


class SystemMetricsResponse(BaseModel):
    """System metrics response."""

    timestamp: str = Field(..., description="Metrics collection timestamp")
    uptime_seconds: float = Field(..., description="API uptime in seconds")
    active_connections: int = Field(
        ..., description="Number of active WebSocket connections"
    )
    job_stats: Dict[str, int] = Field(..., description="Job statistics by status")
    total_jobs: int = Field(..., description="Total number of jobs in system")
    queue_depth: int = Field(..., description="Number of queued jobs")
    running_jobs: int = Field(..., description="Number of currently running jobs")
