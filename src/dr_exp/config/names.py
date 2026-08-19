"""Closed string vocabularies and persisted-format literals.

The literals in this module are persisted identity: they enter ``work_key``
and ``execution_config_reference`` digests, DBOS queue names, and the trainer
request envelope. Golden tests in ``tests/unit/test_identity.py`` pin them
verbatim. Never derive them from field names or enum iteration.
"""

from enum import UNIQUE, StrEnum, auto, verify
from typing import Final


@verify(UNIQUE)
class Accelerator(StrEnum):
    """Accelerator kinds a machine profile may declare."""

    CPU = auto()
    MPS = auto()
    CUDA = auto()


@verify(UNIQUE)
class QueueName(StrEnum):
    """DBOS queue names for the ``train`` stage.

    Persisted format: admission writes these names into the DBOS system
    database, and a worker that declares a different spelling silently never
    dequeues its work.
    """

    TRAIN_CPU = "train-cpu"
    TRAIN_MPS = "train-mps"
    TRAIN_CUDA = "train-cuda"


@verify(UNIQUE)
class RequestField(StrEnum):
    """Keys of the trainer request envelope (``dr-exp/importable-json/v1``)."""

    PARAMS = auto()
    WORKSPACE = auto()
    WORK_KEY = auto()
    ATTEMPT = auto()


@verify(UNIQUE)
class LabelKey(StrEnum):
    """Work-item label keys dr-exp assigns meaning to."""

    ACCELERATOR = auto()


# Persisted-format contract: the pipeline identity recorded in the ledger.
PIPELINE_KEY: Final = "dr-exp-train"
PIPELINE_VERSION: Final = 1
STAGE_KEY: Final = "train"

# Persisted-format contract: the child-process request/result contract version.
TRAINER_CONTRACT: Final = "dr-exp/importable-json/v1"

# Persisted-format contract: keys of the execution-config identity document.
EXECUTION_CONFIG_PIPELINE_FIELD: Final = "pipeline"
EXECUTION_CONFIG_VERSION_FIELD: Final = "version"
EXECUTION_CONFIG_CONTRACT_FIELD: Final = "trainer_contract"

# Persisted-format contract: keys of the work-identity document.
WORK_IDENTITY_ENTRY_POINT_FIELD: Final = "entry_point"
WORK_IDENTITY_PARAMS_FIELD: Final = "params"
WORK_IDENTITY_LABELS_FIELD: Final = "labels"
WORK_IDENTITY_BUDGETS_FIELD: Final = "budgets"

QUEUE_NAME_BY_ACCELERATOR: Final[dict[Accelerator, QueueName]] = {
    Accelerator.CPU: QueueName.TRAIN_CPU,
    Accelerator.MPS: QueueName.TRAIN_MPS,
    Accelerator.CUDA: QueueName.TRAIN_CUDA,
}

__all__ = [
    "EXECUTION_CONFIG_CONTRACT_FIELD",
    "EXECUTION_CONFIG_PIPELINE_FIELD",
    "EXECUTION_CONFIG_VERSION_FIELD",
    "PIPELINE_KEY",
    "PIPELINE_VERSION",
    "QUEUE_NAME_BY_ACCELERATOR",
    "STAGE_KEY",
    "TRAINER_CONTRACT",
    "WORK_IDENTITY_BUDGETS_FIELD",
    "WORK_IDENTITY_ENTRY_POINT_FIELD",
    "WORK_IDENTITY_LABELS_FIELD",
    "WORK_IDENTITY_PARAMS_FIELD",
    "Accelerator",
    "LabelKey",
    "QueueName",
    "RequestField",
]
