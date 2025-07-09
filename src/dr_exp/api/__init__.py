"""Public API for dr_exp."""

from pathlib import Path
from typing import Any

from dr_exp.core.job_db import JobDB


def submit_job(
    base_path: str | Path,
    experiment: str,
    config: dict[str, Any],
    priority: int = 100,
    tags: list[str] | None = None,
) -> str:
    """Submit a job to dr_exp programmatically.

    Args:
        base_path: Base directory for experiments
        experiment: Experiment name
        config: Job configuration dict (must include _target_)
        priority: Job priority (0-1000)
        tags: Optional list of tags

    Returns:
        str: Job ID (UUID)
    """
    job_db = JobDB(base_path, experiment)
    return job_db.create_job(config, priority, tags)


def submit_jobs(
    base_path: str | Path,
    experiment: str,
    configs: list[dict[str, Any]],
    priority: int = 100,
    tags: list[str] | None = None,
) -> list[str]:
    """Submit a job to dr_exp programmatically.

    Args:
        base_path: Base directory for experiments
        experiment: Experiment name
        configs: List of job configuration dict (must include _target_)
        priority: Job priority (0-1000)
        tags: Optional list of tags

    Returns:
        str: Job ID (UUID)
    """
    job_db = JobDB(base_path, experiment)
    return [job_db.create_job(config, priority, tags) for config in configs]


__all__ = ["JobDB", "submit_job", "submit_jobs"]
