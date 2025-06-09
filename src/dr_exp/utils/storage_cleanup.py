from __future__ import annotations

import os
import shutil
from dr_exp.job_db import BaseJobDB
from typing import List
from pathlib import Path


def find_all_storage(client: BaseJobDB) -> List[Path]:
    storage_dir = client.storage_dir
    jobs_dir = client.jobs_dir
    if not os.path.exists(jobs_dir) and not os.path.exists(storage_dir):
        return []

    # TODO: get all the paths that would be deleted and return
    assert False, "finish impl by addressing TODO"
    return []


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


__all__ = ["cleanup_uploaded_runs"]
