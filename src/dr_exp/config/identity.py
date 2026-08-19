"""Content-addressed identity for jobs and execution configuration.

Both digests below are persisted identity: ``work_key`` is the dedupe key
dr-platform stores per campaign, and ``execution_config_reference`` is recorded
on every pipeline run. Their exact document shapes are pinned verbatim by
golden tests; changing a key or a value here silently re-identifies every
future submission and must be a deliberate, tested change.
"""

from __future__ import annotations

from dr_serialize import Jsonable, json_hash

from dr_exp.config.job import JobConfig
from dr_exp.config.names import (
    EXECUTION_CONFIG_CONTRACT_FIELD,
    EXECUTION_CONFIG_PIPELINE_FIELD,
    EXECUTION_CONFIG_VERSION_FIELD,
    PIPELINE_KEY,
    PIPELINE_VERSION,
    TRAINER_CONTRACT,
    WORK_IDENTITY_BUDGETS_FIELD,
    WORK_IDENTITY_ENTRY_POINT_FIELD,
    WORK_IDENTITY_LABELS_FIELD,
    WORK_IDENTITY_PARAMS_FIELD,
)

#: Length of the hex digests used as keys. dr-platform caps keys at 128
#: characters, so a full sha256 hex digest fits with room for a prefix.
_DIGEST_LENGTH = 64


def work_identity_document(config: JobConfig) -> Jsonable:
    """Return the canonical document that identifies one unit of work.

    ``priority`` and ``tags`` are deliberately excluded: they are scheduling
    and annotation metadata, not part of what the job computes, so changing
    them must not create a new work item.
    """
    document: dict[str, Jsonable] = {
        WORK_IDENTITY_ENTRY_POINT_FIELD: config.entry_point,
        WORK_IDENTITY_LABELS_FIELD: dict(config.labels),
        WORK_IDENTITY_PARAMS_FIELD: dict(config.params),
    }
    if config.budgets is not None:
        document[WORK_IDENTITY_BUDGETS_FIELD] = config.budgets.model_dump(mode="json")
    return document


def work_key(config: JobConfig) -> str:
    """Return the dedupe key for one job configuration."""
    return str(json_hash(work_identity_document(config)))


def execution_config_document() -> Jsonable:
    """Return the canonical document identifying this pipeline's contract."""
    return {
        EXECUTION_CONFIG_PIPELINE_FIELD: PIPELINE_KEY,
        EXECUTION_CONFIG_VERSION_FIELD: PIPELINE_VERSION,
        EXECUTION_CONFIG_CONTRACT_FIELD: TRAINER_CONTRACT,
    }


def execution_config_reference() -> str:
    """Return the provenance reference recorded on every pipeline run."""
    return str(json_hash(execution_config_document()))


__all__ = [
    "execution_config_document",
    "execution_config_reference",
    "work_identity_document",
    "work_key",
]
