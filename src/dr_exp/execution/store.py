"""Durable storage for the submitted ``JobConfig`` behind an input reference.

dr-platform treats ``input_reference`` as an opaque string. dr-exp stores the
resolved configuration as one JSON document per work key under the machine
profile's ``workspace_root`` and uses its path as the reference, so a worker on
the same machine can resolve a work item without another database round trip.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from dr_exp.config.job import ConfigError, JobConfig


def store_job_config(config: JobConfig, *, work_key: str, workspace_root: Path) -> str:
    """Persist ``config`` and return its opaque input reference.

    Writing is idempotent: the same work key always carries the same
    configuration, because the work key is that configuration's digest.
    """
    path = workspace_root / "configs" / f"{work_key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    document = config.model_dump(mode="json")
    # A per-writer temp name: two processes submitting the same work key
    # concurrently would otherwise share one scratch file and could rename a
    # half-written document into place.
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(document, indent=2, sort_keys=True))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return str(path)


def load_job_config_reference(reference: str) -> JobConfig:
    """Resolve an input reference written by :func:`store_job_config`."""
    path = Path(reference)
    if not path.is_file():
        raise ConfigError(f"input reference does not name a file: {reference}")
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"input reference is not valid JSON: {reference}: {error}"
        ) from error
    return JobConfig.model_validate(document)


__all__ = ["load_job_config_reference", "store_job_config"]
