from __future__ import annotations

import os
import shutil
from typing import Any


def cleanup_uploaded_runs(client: Any) -> int:
    """Remove run directories with a ``finished.flag`` file.

    Parameters
    ----------
    client : object
        Instance of :class:`SupabaseClient` or :class:`SupabaseMockClient`.

    Returns
    -------
    int
        Number of run directories deleted.
    """
    storage_path = getattr(client, "mock_storage_path", None) or getattr(
        client, "local_storage_path", None
    )
    if not storage_path or not os.path.exists(storage_path):
        return 0

    removed = 0
    for name in os.listdir(storage_path):
        if not name.startswith("run_"):
            continue
        run_dir = os.path.join(storage_path, name)
        if not os.path.isdir(run_dir):
            continue
        flag_path = os.path.join(run_dir, "finished.flag")
        if os.path.exists(flag_path):
            shutil.rmtree(run_dir, ignore_errors=True)
            removed += 1
    return removed


__all__ = ["cleanup_uploaded_runs"]
