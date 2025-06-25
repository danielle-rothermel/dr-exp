"""Simple FastAPI application for remote monitoring."""

import os
from typing import Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from dr_exp.core.job_db import JobDB


app = FastAPI(title="dr_exp API", version="1.0.0")

# Enable CORS for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global JobDB instance (initialized on startup)
job_db: JobDB | None = None


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize JobDB with remote read enabled."""
    global job_db  # noqa: PLW0603

    # Get configuration from environment
    base_path = os.environ.get("DR_EXP_BASE_PATH")
    experiment = os.environ.get("DR_EXP_EXPERIMENT")

    if not base_path or not experiment:
        print("ERROR: DR_EXP_BASE_PATH and DR_EXP_EXPERIMENT must be set")
        return

    # Initialize JobDB
    job_db = JobDB(base_path=base_path, experiment_name=experiment)

    # Enable remote read
    if job_db.enable_remote_read():
        print(f"Remote read enabled for {experiment}")
        print(f"Sync mode: {job_db.sync_mode()}")
    else:
        print("Remote read not available - using local data only")


@app.get("/")
async def root() -> dict[str, Any]:
    """API root endpoint."""
    return {
        "service": "dr_exp API",
        "version": "1.0.0",
        "experiment": job_db.experiment_name if job_db else None,
        "sync_mode": job_db.sync_mode() if job_db else "not_initialized",
    }


@app.get("/experiment/info")
async def get_experiment_info() -> dict[str, Any]:
    """Get experiment information and statistics."""
    if not job_db:
        raise HTTPException(status_code=503, detail="Service not initialized")

    info = job_db.get_experiment_info_remote()
    return info


@app.get("/jobs")
async def list_jobs(
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
    use_remote: bool = Query(default=True, description="Use remote data if available"),
) -> dict[str, Any]:
    """List jobs in the experiment."""
    if not job_db:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if use_remote and job_db.remote_enabled:
        jobs = job_db.list_jobs_remote(status=status)
    else:
        jobs = job_db.list_jobs(status=status)

    # Apply limit
    jobs = jobs[:limit]

    return {
        "jobs": jobs,
        "count": len(jobs),
        "source": "remote" if (use_remote and job_db.remote_enabled) else "local",
    }


@app.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    use_remote: bool = Query(default=True, description="Use remote data if available"),
) -> dict[str, Any]:
    """Get details for a specific job."""
    if not job_db:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if use_remote and job_db.remote_enabled:
        job = job_db.get_job_remote(job_id)
    else:
        job = job_db.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


@app.get("/jobs/{job_id}/artifacts")
async def list_job_artifacts(job_id: str) -> dict[str, Any]:
    """List artifacts for a job."""
    if not job_db or not job_db.remote_enabled:
        raise HTTPException(status_code=503, detail="Remote storage not available")

    try:
        if job_db.remote_client:
            sync_records = job_db.remote_client.get_job_sync_status(job_id)
        else:
            sync_records = []

        artifacts = [
            {
                "file_name": Path(record["file_path"]).name,
                "file_type": record["file_type"],
                "size_bytes": record["size_bytes"],
                "checksum": record["checksum"],
                "uploaded_at": record["completed_at"],
            }
            for record in sync_records
            if record["status"] == "completed"
        ]

        return {"job_id": job_id, "artifacts": artifacts, "count": len(artifacts)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/jobs/{job_id}/download")
async def download_job_artifacts(job_id: str) -> dict[str, Any]:
    """Download all artifacts for a job."""
    if not job_db:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if not job_db.remote_enabled:
        raise HTTPException(status_code=503, detail="Remote storage not available")

    try:
        downloaded = job_db.download_job_artifacts(job_id)

        return {
            "job_id": job_id,
            "downloaded_files": [str(p.name) for p in downloaded],
            "count": len(downloaded),
            "target_dir": str(job_db.get_storage_path(job_id)),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/queue/stats")
async def get_queue_stats() -> dict[str, Any]:
    """Get job queue statistics."""
    if not job_db:
        raise HTTPException(status_code=503, detail="Service not initialized")

    info = job_db.get_experiment_info_remote()

    return {
        "total_jobs": info["total_jobs"],
        "by_status": info["status_counts"],
        "queue_length": info["status_counts"].get("queued", 0),
        "active_jobs": info["status_counts"].get("running", 0),
    }


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    health = {
        "status": "healthy" if job_db else "unhealthy",
        "job_db": job_db is not None,
        "remote_enabled": job_db.remote_enabled if job_db else False,
    }

    if job_db and job_db.remote_enabled and job_db.remote_client:
        try:
            # Test remote connection
            job_db.remote_client.test_connection()
            health["remote_connection"] = True
        except Exception:
            health["remote_connection"] = False

    return health
