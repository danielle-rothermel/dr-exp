from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from cachetools import LRUCache
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from dr_exp.api.models import (
    BoostPriorityRequest,
    ConfigResponse,
    ErrorResponse,
    JobModel,
    KillRequest,
    MetricsResponse,
    PriorityResponse,
    RequeueRequest,
    SetPriorityRequest,
    SuccessResponse,
)
from dr_exp.utils.jobdb_factory import get_job_db_client
from dr_exp.job_db.base_job_db import BaseJobDB

load_dotenv()
logger = logging.getLogger(__name__)


def get_admin_key() -> str:
    """Return the API key used for admin endpoints.

    Returns
    -------
    str
        The value of ``ADMIN_API_KEY`` from the environment or ``"testkey"`` if
        the variable is not set.
    """
    return os.getenv("ADMIN_API_KEY", "testkey")


def verify_api_key(x_api_key: str = Header(...)) -> None:
    """Validate an incoming API key.

    Parameters
    ----------
    x_api_key : str
        The value of the ``X-API-KEY`` header supplied by the client.

    Raises
    ------
    HTTPException
        If the provided key does not match :func:`get_admin_key`.
    """
    if x_api_key != get_admin_key():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid API key"
        )


def raise_job_not_found(job_id: str) -> None:
    """Raise a standardized job not found error.
    
    Parameters
    ----------
    job_id : str
        The job ID that was not found.
        
    Raises
    ------
    HTTPException
        404 error with standardized message.
    """
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Job {job_id} not found"
    )


def raise_config_not_found(job_id: str) -> None:
    """Raise a standardized config not found error.
    
    Parameters
    ----------
    job_id : str
        The job ID whose config was not found.
        
    Raises
    ------
    HTTPException
        404 error with standardized message.
    """
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Configuration for job {job_id} not found"
    )


def raise_metrics_not_found(run_id: str) -> None:
    """Raise a standardized metrics not found error.
    
    Parameters
    ----------
    run_id : str
        The run ID whose metrics were not found.
        
    Raises
    ------
    HTTPException
        404 error with standardized message.
    """
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Metrics for run {run_id} not found"
    )


class MetricsLoader:
    """Load and cache run metrics from storage."""

    def __init__(
        self, client: BaseJobDB, maxsize: int = 32
    ) -> None:
        """Create a loader instance.

        Parameters
        ----------
        client : BaseJobDB
            Client used to retrieve metrics files.
        maxsize : int, optional
            Maximum number of runs to keep in the LRU cache, by default ``32``.
        """
        self.client = client
        self.cache: LRUCache[str, List[Dict[str, Any]]] = LRUCache(maxsize=maxsize)

    def load(self, run_id: str, limit: Optional[int] = 500) -> List[Dict[str, Any]]:
        """Return metrics for a run, loading them if necessary.

        Parameters
        ----------
        run_id : str
            Identifier of the run to load metrics for.
        limit : int, optional
            Maximum number of recent metrics to return, by default 500.
            If None, returns all metrics.

        Returns
        -------
        list[dict[str, Any]]
            Parsed metrics loaded from storage.

        Raises
        ------
        FileNotFoundError
            If the metrics file for ``run_id`` does not exist.
        """
        # Use cache key that includes the limit to avoid cache misses
        cache_key = f"{run_id}:{limit}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Use the abstract interface method instead of direct file access
        metrics = self.client.get_metrics(run_id, limit=limit)
        self.cache[cache_key] = metrics
        return metrics


def create_app(base_path: str = ".") -> FastAPI:
    """Create and configure the FastAPI application instance.

    Parameters
    ----------
    base_path : str, optional
        Base path used when instantiating a mock Supabase client. Defaults to
        the current directory.

    Returns
    -------
    FastAPI
        A fully configured application ready to run.
    """
    app = FastAPI()

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Vite dev server default port
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    client = get_job_db_client()
    loader = MetricsLoader(client)

    app.state.client = client
    app.state.loader = loader

    @app.get("/jobs", response_model=List[JobModel])
    async def list_jobs() -> List[JobModel]:
        """Return a list of available jobs."""
        jobs = client.list_jobs()
        return [JobModel.model_validate(j) for j in jobs]

    @app.get("/job/{job_id}", response_model=JobModel)
    async def get_job(job_id: str) -> JobModel:
        """Retrieve details for a specific job."""
        job = client.get_job_details(job_id)
        if job is None:
            raise_job_not_found(job_id)
        return JobModel.model_validate(job)

    @app.get("/config/{job_id}", response_model=ConfigResponse)
    async def get_config(job_id: str) -> ConfigResponse:
        """Return the configuration associated with ``job_id``."""
        cfg = client.get_config_for_job(job_id)
        if cfg is None:
            raise_config_not_found(job_id)
        return ConfigResponse(config=cfg)

    @app.get("/metrics/{run_id}", response_model=MetricsResponse)
    async def get_metrics(run_id: str, limit: Optional[int] = 500) -> MetricsResponse:
        """Fetch metrics for the given run.
        
        Parameters
        ----------
        limit : int, optional
            Maximum number of recent metrics to return, by default 500.
            Set to None to return all metrics.
        """
        try:
            metrics = loader.load(run_id, limit=limit)
        except FileNotFoundError:
            raise_metrics_not_found(run_id)
        return MetricsResponse(metrics=metrics)

    @app.post("/job/kill", dependencies=[Depends(verify_api_key)], response_model=SuccessResponse)
    async def kill_job(req: KillRequest) -> SuccessResponse:
        """Mark ``job_id`` as killed."""
        job = client.get_job_details(req.job_id)
        if job is None:
            raise_job_not_found(req.job_id)
        
        logger.info("Kill requested for job %s", req.job_id)
        result = client.update_job(req.job_id, {"kill_requested": True})
        
        if not result.get("success", True):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to kill job {req.job_id}: {result.get('error', 'Unknown error')}"
            )
        
        return SuccessResponse(
            message=f"Job {req.job_id} marked for termination",
            job_id=req.job_id
        )

    @app.post("/job/requeue", dependencies=[Depends(verify_api_key)], response_model=SuccessResponse)
    async def requeue_job(req: RequeueRequest) -> SuccessResponse:
        """Requeue ``job_id`` for another attempt."""
        job = client.get_job_details(req.job_id)
        if job is None:
            raise_job_not_found(req.job_id)
        
        retry = job.get("retry_index", 0) + 1
        logger.info("Requeue requested for job %s", req.job_id)
        result = client.update_job(req.job_id, {"status": "queued", "retry_index": retry})
        
        if not result.get("success", True):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to requeue job {req.job_id}: {result.get('error', 'Unknown error')}"
            )
        
        return SuccessResponse(
            message=f"Job {req.job_id} requeued for retry (attempt {retry})",
            job_id=req.job_id
        )

    @app.post("/job/boost-priority", dependencies=[Depends(verify_api_key)], response_model=PriorityResponse)
    async def boost_priority(req: BoostPriorityRequest) -> PriorityResponse:
        """Boost the priority of a job by the specified amount."""
        job = client.get_job_details(req.job_id)
        if job is None:
            raise_job_not_found(req.job_id)
        
        old_priority = job.get("priority", 100)
        logger.info("Priority boost requested for job %s: +%d", req.job_id, req.boost_amount)
        
        try:
            result = client.boost_job_priority(req.job_id, req.boost_amount)
            new_priority = result.get("new_priority", old_priority)
            
            return PriorityResponse(
                job_id=req.job_id,
                old_priority=old_priority,
                new_priority=new_priority,
                success=result.get("success", False),
                message=result.get("message", "Priority boosted successfully")
            )
        except Exception as e:
            logger.error("Error boosting priority for job %s: %s", req.job_id, e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to boost priority for job {req.job_id}: {str(e)}"
            )

    @app.post("/job/set-priority", dependencies=[Depends(verify_api_key)], response_model=PriorityResponse)
    async def set_priority(req: SetPriorityRequest) -> PriorityResponse:
        """Set the absolute priority of a job."""
        job = client.get_job_details(req.job_id)
        if job is None:
            raise_job_not_found(req.job_id)
        
        old_priority = job.get("priority", 100)
        logger.info("Priority set requested for job %s: %d (reason: %s)", req.job_id, req.priority, req.reason)
        
        try:
            result = client.update_job_priority(req.job_id, req.priority, req.reason)
            new_priority = result.get("new_priority", req.priority)
            
            return PriorityResponse(
                job_id=req.job_id,
                old_priority=old_priority,
                new_priority=new_priority,
                success=result.get("success", False),
                message=result.get("message", "Priority set successfully")
            )
        except Exception as e:
            logger.error("Error setting priority for job %s: %s", req.job_id, e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to set priority for job {req.job_id}: {str(e)}"
            )

    return app


# Global app instance - only create when running as a script
if __name__ == "__main__":
    app = create_app()
else:
    # Create a default app for import contexts - tests should use create_app() directly
    app = None
