from __future__ import annotations

import json
import logging
import os
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from enum import Enum

from dotenv import load_dotenv

from cachetools import LRUCache
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    status,
    Security,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from dr_exp.api.models import (
    BoostPriorityRequest,
    ConfigResponse,
    HealthResponse,
    JobModel,
    KillRequest,
    MetricsResponse,
    PaginatedJobsResponse,
    PriorityResponse,
    RequeueRequest,
    SetPriorityRequest,
    SuccessResponse,
    SystemMetricsResponse,
)
from dr_exp.utils.jobdb_factory import get_job_db_client
from dr_exp.job_db.base_job_db import BaseJobDB

load_dotenv()
logger = logging.getLogger(__name__)

# Track API startup time for health checks
API_STARTUP_TIME = time.time()


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
        logger.info(
            f"WebSocket connected. Total connections: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(
            f"WebSocket disconnected. Total connections: {len(self.active_connections)}"
        )

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send a message to a specific WebSocket connection."""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Critical WebSocket failure sending message: {e}")
            self.disconnect(websocket)
            raise RuntimeError(f"WebSocket communication failed: {e}") from e

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
                logger.error(f"Critical WebSocket failure during broadcast: {e}")
                disconnected.add(connection)
                # Continue with other connections but track failures

        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)


def get_admin_key() -> str:
    """Return the API key used for admin endpoints.

    Returns
    -------
    str
        The value of ``ADMIN_API_KEY`` from the environment.
        
    Raises
    ------
    RuntimeError
        If ADMIN_API_KEY environment variable is not set.
    """
    key = os.getenv("ADMIN_API_KEY")
    if key is None:
        raise RuntimeError("ADMIN_API_KEY environment variable must be set")
    return key


def get_reader_key() -> str:
    """Return the API key used for read-only endpoints.

    Returns
    -------
    str
        The value of ``READER_API_KEY`` from the environment.
        
    Raises
    ------
    RuntimeError
        If READER_API_KEY environment variable is not set.
    """
    key = os.getenv("READER_API_KEY")
    if key is None:
        raise RuntimeError("READER_API_KEY environment variable must be set")
    return key


def authenticate_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> UserRole:
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
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return user_role


def require_reader_or_admin(
    user_role: UserRole = Depends(authenticate_user),
) -> UserRole:
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


def get_job_statistics(client: BaseJobDB) -> Dict[str, int]:
    """Get job statistics by status.

    Parameters
    ----------
    client : BaseJobDB
        Database client to query jobs from.

    Returns
    -------
    Dict[str, int]
        Dictionary mapping status names to counts.
    """
    try:
        jobs = client.list_jobs()
        status_counts = Counter(job.get("status", "unknown") for job in jobs)

        # Ensure all standard statuses are represented
        for status in ["queued", "running", "completed", "failed", "killed"]:
            if status not in status_counts:
                status_counts[status] = 0

        return dict(status_counts)
    except Exception as e:
        logger.error(f"Error collecting job statistics: {e}")
        return {"error": 1}


def check_database_health(client: BaseJobDB) -> str:
    """Check if database is accessible.

    Parameters
    ----------
    client : BaseJobDB
        Database client to test.

    Returns
    -------
    str
        Status string: "healthy" or "unhealthy".
    """
    try:
        # Try a simple operation to verify database connectivity
        client.has_queued_jobs()
        return "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return "unhealthy"


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
        status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found"
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
        detail=f"Configuration for job {job_id} not found",
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
        detail=f"Metrics for run {run_id} not found",
    )


def filter_and_sort_jobs(
    jobs: List[Dict[str, Any]],
    status: Optional[str] = None,
    priority_min: Optional[int] = None,
    priority_max: Optional[int] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> List[Dict[str, Any]]:
    """Filter and sort a list of jobs.

    Parameters
    ----------
    jobs : List[Dict[str, Any]]
        Complete list of jobs to filter and sort.
    status : str, optional
        Filter by job status (queued, running, completed, failed, killed).
    priority_min : int, optional
        Minimum priority threshold (inclusive).
    priority_max : int, optional
        Maximum priority threshold (inclusive).
    sort_by : str, optional
        Field to sort by, by default "created_at".
        Valid values: created_at, priority, status, retry_index
    sort_order : str, optional
        Sort order, by default "desc". Valid values: asc, desc

    Returns
    -------
    List[Dict[str, Any]]
        Filtered and sorted list of jobs.
    """
    filtered_jobs = jobs.copy()

    # Apply status filter
    if status:
        filtered_jobs = [job for job in filtered_jobs if job.get("status") == status]

    # Apply priority filters
    if priority_min is not None:
        filtered_jobs = [
            job
            for job in filtered_jobs
            if job["priority"] >= priority_min  # Fail fast if priority missing
        ]

    if priority_max is not None:
        filtered_jobs = [
            job
            for job in filtered_jobs
            if job["priority"] <= priority_max  # Fail fast if priority missing
        ]

    # Apply sorting
    valid_sort_fields = {"created_at", "priority", "status", "retry_index"}
    if sort_by not in valid_sort_fields:
        sort_by = "created_at"

    reverse = sort_order.lower() == "desc"

    if sort_by == "priority":
        filtered_jobs.sort(
            key=lambda job: job["priority"],
            reverse=reverse,  # Fail fast if priority missing
        )
    elif sort_by == "retry_index":
        filtered_jobs.sort(
            key=lambda job: job["retry_index"], reverse=reverse
        )
    elif sort_by == "status":
        filtered_jobs.sort(key=lambda job: job["status"], reverse=reverse)
    else:  # created_at
        filtered_jobs.sort(
            key=lambda job: job["created_at"], reverse=reverse
        )

    return filtered_jobs


def paginate_jobs(
    jobs: List[Dict[str, Any]], page: int, per_page: int
) -> PaginatedJobsResponse:
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
        has_prev=page > 1,
    )


class MetricsLoader:
    """Load and cache run metrics from storage."""

    def __init__(self, client: BaseJobDB, maxsize: int = 32) -> None:
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
        description="""
        ## API for Managing Deep Learning Experiments
        
        This API provides comprehensive management for deep learning experiment workflows,
        including job queuing, priority management, metrics collection, and real-time monitoring.
        
        ### Features
        - **Job Management**: Queue, execute, and monitor experiment jobs
        - **Priority System**: Advanced job prioritization with boost capabilities (0-1000 scale)
        - **Real-time Updates**: WebSocket support for live job status updates
        - **Metrics Collection**: Comprehensive experiment metrics and artifact storage
        - **Authentication**: Role-based access control with admin and reader roles
        - **Monitoring**: Health checks and system metrics for observability
        - **Filtering & Pagination**: Advanced job listing with search capabilities
        
        ### Authentication
        All admin endpoints require Bearer token authentication:
        - **Admin Role**: Full access to job management and priority controls
        - **Reader Role**: Read-only access to job data and metrics
        
        ### Job Priority System
        Jobs are processed by priority (0-1000, higher = more urgent):
        - **SYSTEM (900-1000)**: Critical system operations
        - **URGENT (700-899)**: High-priority research experiments  
        - **HIGH (500-699)**: Important experiments
        - **NORMAL (200-499)**: Standard experiments (default: 100)
        - **LOW (0-199)**: Background/cleanup jobs
        
        ### WebSocket Real-time Updates
        Connect to `/ws` for real-time job status updates and system notifications.
        """,
        version="1.0.0",
        contact={
            "name": "DR Experiment Manager",
            "url": "https://github.com/your-org/dr-exp",
        },
        license_info={
            "name": "MIT",
        },
        openapi_tags=[
            {"name": "jobs", "description": "Job management and querying operations"},
            {
                "name": "admin",
                "description": "Administrative operations requiring elevated permissions",
            },
            {"name": "monitoring", "description": "Health checks and system metrics"},
            {"name": "websocket", "description": "Real-time communication endpoints"},
        ],
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

    # Add request logging middleware
    @app.middleware("http")
    async def request_logging_middleware(request, call_next):
        start_time = time.time()

        # Log request
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            f"Request started: {request.method} {request.url.path} from {client_ip}"
        )

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            # Log response
            logger.info(
                f"Request completed: {request.method} {request.url.path} "
                f"-> {response.status_code} in {process_time:.3f}s"
            )

            # Add timing header
            response.headers["X-Process-Time"] = str(process_time)
            return response

        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"Request failed: {request.method} {request.url.path} "
                f"after {process_time:.3f}s - {str(e)}"
            )
            raise

    client = get_job_db_client()
    loader = MetricsLoader(client)
    manager = ConnectionManager()

    app.state.client = client
    app.state.loader = loader
    app.state.manager = manager

    # Add API info endpoint
    @app.get("/api", tags=["api-info"])
    async def api_info():
        """Get API version information and available endpoints."""
        return {
            "name": "DR Experiment Manager API",
            "version": "1.0.0",
            "versions": {
                "v1": {"status": "stable", "prefix": "/api/v1", "docs": "/docs"}
            },
            "health_check": "/health",
            "metrics": "/metrics",
            "websocket": "/ws",
        }

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

    @app.get("/jobs", tags=["jobs"])
    async def list_jobs(
        page: int = 1,
        per_page: int = 20,
        paginated: bool = False,
        job_status: Optional[str] = None,
        priority_min: Optional[int] = None,
        priority_max: Optional[int] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ):
        """Return a list of available jobs with optional pagination, filtering, and sorting.

        Parameters
        ----------
        page : int, optional
            Page number (1-based), by default 1
        per_page : int, optional
            Number of jobs per page, by default 20
        paginated : bool, optional
            Whether to return paginated response with metadata, by default False
            If False, returns simple list
        job_status : str, optional
            Filter by job status (queued, running, completed, failed, killed)
        priority_min : int, optional
            Minimum priority threshold (inclusive)
        priority_max : int, optional
            Maximum priority threshold (inclusive)
        sort_by : str, optional
            Field to sort by, by default "created_at"
            Valid values: created_at, priority, status, retry_index
        sort_order : str, optional
            Sort order, by default "desc". Valid values: asc, desc
        """
        jobs = client.list_jobs()

        # Apply filtering and sorting
        jobs = filter_and_sort_jobs(
            jobs,
            status=job_status,
            priority_min=priority_min,
            priority_max=priority_max,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        if paginated:
            # Validate pagination parameters
            if page < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Page number must be >= 1",
                )
            if per_page < 1 or per_page > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="per_page must be between 1 and 100",
                )

            # Validate filter parameters
            valid_statuses = {"queued", "running", "completed", "failed", "killed"}
            if job_status and job_status not in valid_statuses:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Valid values: {', '.join(valid_statuses)}",
                )

            if priority_min is not None and (priority_min < 0 or priority_min > 1000):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="priority_min must be between 0 and 1000",
                )

            if priority_max is not None and (priority_max < 0 or priority_max > 1000):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="priority_max must be between 0 and 1000",
                )

            if (
                priority_min is not None
                and priority_max is not None
                and priority_min > priority_max
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="priority_min cannot be greater than priority_max",
                )

            valid_sort_fields = {"created_at", "priority", "status", "retry_index"}
            if sort_by not in valid_sort_fields:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort_by. Valid values: {', '.join(valid_sort_fields)}",
                )

            if sort_order.lower() not in {"asc", "desc"}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="sort_order must be 'asc' or 'desc'",
                )

            return paginate_jobs(jobs, page, per_page)
        else:
            # Return simple list (with filters/sorting still applied)
            return [JobModel.model_validate(j) for j in jobs]

    @app.get("/job/{job_id}", response_model=JobModel, tags=["jobs"])
    async def get_job(job_id: str) -> JobModel:
        """Retrieve details for a specific job."""
        job = client.get_job_details(job_id)
        if job is None:
            raise_job_not_found(job_id)
        return JobModel.model_validate(job)

    @app.get("/config/{job_id}", response_model=ConfigResponse, tags=["jobs"])
    async def get_config(job_id: str) -> ConfigResponse:
        """Return the configuration associated with ``job_id``."""
        cfg = client.get_config_for_job(job_id)
        if cfg is None:
            raise_config_not_found(job_id)
        return ConfigResponse(config=cfg)

    @app.get("/metrics/{run_id}", response_model=MetricsResponse, tags=["jobs"])
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
        return MetricsResponse(metrics=metrics, count=len(metrics))

    @app.post(
        "/job/kill",
        dependencies=[Depends(require_admin)],
        response_model=SuccessResponse,
        tags=["admin"],
    )
    async def kill_job(req: KillRequest) -> SuccessResponse:
        """Mark ``job_id`` as killed."""
        job = client.get_job_details(req.job_id)
        if job is None:
            raise_job_not_found(req.job_id)

        logger.info("Kill requested for job %s", req.job_id)
        result = client.update_job(req.job_id, {"kill_requested": True})

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to kill job {req.job_id}: {result['error']}",
            )

        # Broadcast job update via WebSocket
        await manager.broadcast(
            {
                "type": "job_update",
                "job_id": req.job_id,
                "action": "kill_requested",
                "message": f"Job {req.job_id} marked for termination",
            }
        )

        return SuccessResponse(
            message=f"Job {req.job_id} marked for termination", job_id=req.job_id
        )

    @app.post(
        "/job/requeue",
        dependencies=[Depends(require_admin)],
        response_model=SuccessResponse,
        tags=["admin"],
    )
    async def requeue_job(req: RequeueRequest) -> SuccessResponse:
        """Requeue ``job_id`` for another attempt."""
        job = client.get_job_details(req.job_id)
        if job is None:
            raise_job_not_found(req.job_id)

        retry = job["retry_index"] + 1
        logger.info("Requeue requested for job %s", req.job_id)
        result = client.update_job(
            req.job_id, {"status": "queued", "retry_index": retry}
        )

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to requeue job {req.job_id}: {result['error']}",
            )

        # Broadcast job update via WebSocket
        await manager.broadcast(
            {
                "type": "job_update",
                "job_id": req.job_id,
                "action": "requeued",
                "retry_index": retry,
                "message": f"Job {req.job_id} requeued for retry (attempt {retry})",
            }
        )

        return SuccessResponse(
            message=f"Job {req.job_id} requeued for retry (attempt {retry})",
            job_id=req.job_id,
        )

    @app.post(
        "/job/boost-priority",
        dependencies=[Depends(require_admin)],
        response_model=PriorityResponse,
        tags=["admin"],
    )
    async def boost_priority(req: BoostPriorityRequest) -> PriorityResponse:
        """Boost the priority of a job by the specified amount."""
        job = client.get_job_details(req.job_id)
        if job is None:
            raise_job_not_found(req.job_id)

        old_priority = job["priority"]  # Fail fast if priority missing
        logger.info(
            "Priority boost requested for job %s: +%d", req.job_id, req.boost_amount
        )

        try:
            result = client.boost_job_priority(req.job_id, req.boost_amount)
            new_priority = result[
                "new_priority"
            ]  # Fail fast if operation result incomplete

            # Broadcast priority update via WebSocket
            await manager.broadcast(
                {
                    "type": "job_update",
                    "job_id": req.job_id,
                    "action": "priority_boosted",
                    "old_priority": old_priority,
                    "new_priority": new_priority,
                    "boost_amount": req.boost_amount,
                    "message": f"Job {req.job_id} priority boosted by {req.boost_amount}",
                }
            )

            return PriorityResponse(
                job_id=req.job_id,
                old_priority=old_priority,
                new_priority=new_priority,
                success=result.get("success", False),
                message=result.get("message", "Priority boosted successfully"),
            )
        except Exception as e:
            logger.error("Error boosting priority for job %s: %s", req.job_id, e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to boost priority for job {req.job_id}: {str(e)}",
            )

    @app.post(
        "/job/set-priority",
        dependencies=[Depends(require_admin)],
        response_model=PriorityResponse,
        tags=["admin"],
    )
    async def set_priority(req: SetPriorityRequest) -> PriorityResponse:
        """Set the absolute priority of a job."""
        job = client.get_job_details(req.job_id)
        if job is None:
            raise_job_not_found(req.job_id)

        old_priority = job["priority"]  # Fail fast if priority missing
        logger.info(
            "Priority set requested for job %s: %d (reason: %s)",
            req.job_id,
            req.priority,
            req.reason,
        )

        try:
            result = client.update_job_priority(req.job_id, req.priority, req.reason)
            new_priority = result[
                "new_priority"
            ]  # Fail fast if operation result incomplete

            # Broadcast priority update via WebSocket
            await manager.broadcast(
                {
                    "type": "job_update",
                    "job_id": req.job_id,
                    "action": "priority_set",
                    "old_priority": old_priority,
                    "new_priority": new_priority,
                    "reason": req.reason,
                    "message": f"Job {req.job_id} priority set to {req.priority}",
                }
            )

            return PriorityResponse(
                job_id=req.job_id,
                old_priority=old_priority,
                new_priority=new_priority,
                success=result.get("success", False),
                message=result.get("message", "Priority set successfully"),
            )
        except Exception as e:
            logger.error("Error setting priority for job %s: %s", req.job_id, e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to set priority for job {req.job_id}: {str(e)}",
            )

    @app.get("/health", response_model=HealthResponse, tags=["monitoring"])
    async def health_check() -> HealthResponse:
        """Check API health status and basic system information."""
        current_time = datetime.now(timezone.utc)
        uptime = time.time() - API_STARTUP_TIME

        # Check database health
        db_status = check_database_health(client)

        # Get job statistics
        job_stats = get_job_statistics(client)

        # Determine overall health status
        overall_status = (
            "healthy"
            if db_status == "healthy" and "error" not in job_stats
            else "unhealthy"
        )

        return HealthResponse(
            status=overall_status,
            timestamp=current_time.isoformat(),
            uptime_seconds=uptime,
            version="1.0.0",
            database_status=db_status,
            job_stats=job_stats,
        )

    @app.get("/metrics", response_model=SystemMetricsResponse, tags=["monitoring"])
    async def system_metrics() -> SystemMetricsResponse:
        """Get detailed system metrics for monitoring and observability."""
        current_time = datetime.now(timezone.utc)
        uptime = time.time() - API_STARTUP_TIME

        # Get job statistics
        job_stats = get_job_statistics(client)
        total_jobs = sum(job_stats.values()) if "error" not in job_stats else 0
        queue_depth = job_stats.get("queued", 0)
        running_jobs = job_stats.get("running", 0)

        # Get active WebSocket connections count
        active_connections = len(manager.active_connections)

        return SystemMetricsResponse(
            timestamp=current_time.isoformat(),
            uptime_seconds=uptime,
            active_connections=active_connections,
            job_stats=job_stats,
            total_jobs=total_jobs,
            queue_depth=queue_depth,
            running_jobs=running_jobs,
        )

    # Add version deprecation headers middleware
    @app.middleware("http")
    async def add_version_headers(request, call_next):
        response = await call_next(request)

        # Add version headers to all responses
        response.headers["X-API-Version"] = "1.0.0"

        # Add deprecation notice for non-versioned endpoints (except health/metrics/ws)
        path = request.url.path
        if not path.startswith("/api/") and path not in [
            "/health",
            "/metrics",
            "/ws",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]:
            response.headers["X-API-Deprecation-Notice"] = (
                "Unversioned endpoints are deprecated. Use /api/v1 prefix."
            )
            response.headers["X-API-Migration-Guide"] = (
                "Replace /jobs with /api/v1/jobs, etc."
            )

        return response

    return app


# Global app instance - only create when running as a script
if __name__ == "__main__":
    app = create_app()
else:
    # Create a default app for import contexts - tests should use create_app() directly
    app = None
