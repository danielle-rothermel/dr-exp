from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Set
from enum import Enum

from dotenv import load_dotenv

from cachetools import LRUCache
from fastapi import Depends, FastAPI, Header, HTTPException, status, Security, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from dr_exp.api.models import (
    BoostPriorityRequest,
    ConfigResponse,
    ErrorResponse,
    JobModel,
    KillRequest,
    MetricsResponse,
    PaginatedJobsResponse,
    PriorityResponse,
    RequeueRequest,
    SetPriorityRequest,
    SuccessResponse,
)
from dr_exp.utils.jobdb_factory import get_job_db_client
from dr_exp.job_db.base_job_db import BaseJobDB

load_dotenv()
logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """User roles for API access control."""
    ADMIN = "admin"
    READER = "reader"


# Security scheme for Bearer token authentication
security = HTTPBearer()


class ConnectionManager:
    """WebSocket connection manager for real-time updates."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send a message to a specific WebSocket connection."""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return
        
        message_text = json.dumps(message)
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_text)
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.add(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)


def get_admin_key() -> str:
    """Return the API key used for admin endpoints.

    Returns
    -------
    str
        The value of ``ADMIN_API_KEY`` from the environment or ``"testkey"`` if
        the variable is not set.
    """
    return os.getenv("ADMIN_API_KEY", "testkey")


def get_reader_key() -> str:
    """Return the API key used for read-only endpoints.

    Returns
    -------
    str
        The value of ``READER_API_KEY`` from the environment or ``"readkey"`` if
        the variable is not set.
    """
    return os.getenv("READER_API_KEY", "readkey")


def authenticate_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> UserRole:
    """Authenticate a user and return their role.
    
    Parameters
    ----------
    credentials : HTTPAuthorizationCredentials
        Bearer token credentials from the Authorization header.
        
    Returns
    -------
    UserRole
        The authenticated user's role.
        
    Raises
    ------
    HTTPException
        If the token is invalid or missing.
    """
    token = credentials.credentials
    
    # Check for admin access
    if token == get_admin_key():
        return UserRole.ADMIN
    
    # Check for reader access
    if token == get_reader_key():
        return UserRole.READER
    
    # Invalid token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin(user_role: UserRole = Depends(authenticate_user)) -> UserRole:
    """Dependency that requires admin role.
    
    Parameters
    ----------
    user_role : UserRole
        The authenticated user's role.
        
    Returns
    -------
    UserRole
        The user's role if they are an admin.
        
    Raises
    ------
    HTTPException
        If the user is not an admin.
    """
    if user_role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user_role


def require_reader_or_admin(user_role: UserRole = Depends(authenticate_user)) -> UserRole:
    """Dependency that requires reader or admin role.
    
    Parameters
    ----------
    user_role : UserRole
        The authenticated user's role.
        
    Returns
    -------
    UserRole
        The user's role if they have read access.
        
    Raises
    ------
    HTTPException
        If the user has no valid role.
    """
    # Both reader and admin roles have read access
    return user_role




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


def paginate_jobs(jobs: List[Dict[str, Any]], page: int, per_page: int) -> PaginatedJobsResponse:
    """Paginate a list of jobs.
    
    Parameters
    ----------
    jobs : List[Dict[str, Any]]
        Complete list of jobs to paginate.
    page : int
        Page number (1-based).
    per_page : int
        Number of jobs per page.
        
    Returns
    -------
    PaginatedJobsResponse
        Paginated response with metadata.
    """
    import math
    
    total = len(jobs)
    pages = math.ceil(total / per_page) if per_page > 0 else 0
    
    # Calculate offset
    start = (page - 1) * per_page
    end = start + per_page
    
    # Slice the jobs list
    paginated_jobs = jobs[start:end]
    
    return PaginatedJobsResponse(
        jobs=[JobModel.model_validate(job) for job in paginated_jobs],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1
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
    app = FastAPI(
        title="DR Experiment Manager API",
        description="API for managing deep learning experiments",
        version="1.0.0"
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Vite dev server default port
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add security headers middleware
    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    client = get_job_db_client()
    loader = MetricsLoader(client)
    manager = ConnectionManager()

    app.state.client = client
    app.state.loader = loader
    app.state.manager = manager

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time job updates."""
        await manager.connect(websocket)
        try:
            while True:
                # Keep connection alive and listen for client messages
                data = await websocket.receive_text()
                # Echo back for now - could be used for client commands later
                await manager.send_personal_message(f"Echo: {data}", websocket)
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    @app.get("/jobs")
    async def list_jobs(
        page: int = 1, 
        per_page: int = 20,
        paginated: bool = False
    ):
        """Return a list of available jobs with optional pagination.
        
        Parameters
        ----------
        page : int, optional
            Page number (1-based), by default 1
        per_page : int, optional
            Number of jobs per page, by default 20
        paginated : bool, optional
            Whether to return paginated response with metadata, by default False
            If False, returns simple list for backward compatibility
        """
        jobs = client.list_jobs()
        
        if paginated:
            # Validate pagination parameters
            if page < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Page number must be >= 1"
                )
            if per_page < 1 or per_page > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="per_page must be between 1 and 100"
                )
            
            return paginate_jobs(jobs, page, per_page)
        else:
            # Backward compatibility: return simple list
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

    @app.post("/job/kill", dependencies=[Depends(require_admin)], response_model=SuccessResponse)
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
        
        # Broadcast job update via WebSocket
        await manager.broadcast({
            "type": "job_update",
            "job_id": req.job_id,
            "action": "kill_requested",
            "message": f"Job {req.job_id} marked for termination"
        })
        
        return SuccessResponse(
            message=f"Job {req.job_id} marked for termination",
            job_id=req.job_id
        )

    @app.post("/job/requeue", dependencies=[Depends(require_admin)], response_model=SuccessResponse)
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
        
        # Broadcast job update via WebSocket
        await manager.broadcast({
            "type": "job_update",
            "job_id": req.job_id,
            "action": "requeued",
            "retry_index": retry,
            "message": f"Job {req.job_id} requeued for retry (attempt {retry})"
        })
        
        return SuccessResponse(
            message=f"Job {req.job_id} requeued for retry (attempt {retry})",
            job_id=req.job_id
        )

    @app.post("/job/boost-priority", dependencies=[Depends(require_admin)], response_model=PriorityResponse)
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
            
            # Broadcast priority update via WebSocket
            await manager.broadcast({
                "type": "job_update",
                "job_id": req.job_id,
                "action": "priority_boosted",
                "old_priority": old_priority,
                "new_priority": new_priority,
                "boost_amount": req.boost_amount,
                "message": f"Job {req.job_id} priority boosted by {req.boost_amount}"
            })
            
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

    @app.post("/job/set-priority", dependencies=[Depends(require_admin)], response_model=PriorityResponse)
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
            
            # Broadcast priority update via WebSocket
            await manager.broadcast({
                "type": "job_update",
                "job_id": req.job_id,
                "action": "priority_set",
                "old_priority": old_priority,
                "new_priority": new_priority,
                "reason": req.reason,
                "message": f"Job {req.job_id} priority set to {req.priority}"
            })
            
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
