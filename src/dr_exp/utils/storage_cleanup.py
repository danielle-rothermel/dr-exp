from __future__ import annotations

import os
import shutil
from dr_exp.job_db import BaseJobDB
from typing import List
from pathlib import Path


def find_all_storage(client: BaseJobDB) -> List[Path]:
    """Find all storage directories that would be cleaned up.

    Args:
        client: JobDB client instance

    Returns:
        List of all paths that would be deleted
    """
    paths_to_delete = []
    
    # In the new simplified architecture, the experiment directory contains:
    # - jobs/       (job metadata)
    # - storage/    (job artifacts)
    # - sync_queue/ (pending syncs)
    
    # The experiment path is the parent of jobs_dir
    experiment_path = Path(client.jobs_dir).parent
    
    # Check if experiment directory exists
    if experiment_path.exists():
        # Add the entire experiment directory since we want to clean everything
        paths_to_delete.append(experiment_path)
    
    # Also check for any legacy paths that might exist
    # (in case of partial migration or old data)
    storage_dir = Path(client.storage_dir)
    jobs_dir = Path(client.jobs_dir)
    
    if storage_dir.exists() and storage_dir != experiment_path / "storage":
        # This is a legacy storage_dir outside the experiment directory
        paths_to_delete.append(storage_dir)
    
    if jobs_dir.exists() and jobs_dir != experiment_path / "jobs":
        # This is a legacy jobs_dir outside the experiment directory
        paths_to_delete.append(jobs_dir)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_paths = []
    for path in paths_to_delete:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)
    
    return unique_paths


def cleanup_uploaded_runs(client: BaseJobDB) -> int:
    """Remove run directories with a ``finished.flag`` file.

    Parameters
    ----------
    client : object
        Instance of :class:`BaseJobDB`.

    Returns
    -------
    int
        Number of run directories deleted.
    """
    jobs_dir = client.jobs_dir
    if not os.path.exists(jobs_dir):
        return 0

    removed = 0
    for name in os.listdir(jobs_dir):
        if not name.startswith("run_"):
            continue
        run_dir = os.path.join(jobs_dir, name)
        if not os.path.isdir(run_dir):
            continue
        flag_path = os.path.join(run_dir, "finished.flag")
        if os.path.exists(flag_path):
            shutil.rmtree(run_dir, ignore_errors=True)
            removed += 1
    return removed


__all__ = ["cleanup_uploaded_runs", "find_all_storage"]
