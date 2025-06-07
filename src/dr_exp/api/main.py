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
    ConfigResponse,
    JobModel,
    KillRequest,
    MetricsResponse,
    RequeueRequest,
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
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
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
            raise HTTPException(status_code=404, detail="Job not found")
        return JobModel.model_validate(job)

    @app.get("/config/{job_id}", response_model=ConfigResponse)
    async def get_config(job_id: str) -> ConfigResponse:
        """Return the configuration associated with ``job_id``."""
        cfg = client.get_config_for_job(job_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="Config not found")
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
            raise HTTPException(status_code=404, detail="Metrics not found")
        return MetricsResponse(metrics=metrics)

    @app.post("/job/kill", dependencies=[Depends(verify_api_key)])
    async def kill_job(req: KillRequest) -> Dict[str, Any]:
        """Mark ``job_id`` as killed."""
        job = client.get_job_details(req.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        logger.info("Kill requested for job %s", req.job_id)
        client.update_job(req.job_id, {"kill_requested": True})
        return {"status": "ok"}

    @app.post("/job/requeue", dependencies=[Depends(verify_api_key)])
    async def requeue_job(req: RequeueRequest) -> Dict[str, Any]:
        """Requeue ``job_id`` for another attempt."""
        job = client.get_job_details(req.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        retry = job.get("retry_index", 0) + 1
        logger.info("Requeue requested for job %s", req.job_id)
        client.update_job(req.job_id, {"status": "queued", "retry_index": retry})
        return {"status": "ok"}

    return app


# Global app instance - only create when running as a script
if __name__ == "__main__":
    app = create_app()
else:
    # Create a default app for import contexts - tests should use create_app() directly
    app = None
