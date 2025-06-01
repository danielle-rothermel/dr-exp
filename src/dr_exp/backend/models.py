from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict


class KillRequest(BaseModel):
    job_id: str


class RequeueRequest(BaseModel):
    job_id: str


class MetricsResponse(BaseModel):
    metrics: List[Dict[str, Any]]


class JobModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    status: str
    retry_index: int | None = None


class ConfigResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    config: Dict[str, Any]
