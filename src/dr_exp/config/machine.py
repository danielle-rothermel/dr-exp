"""Machine profiles: everything host-specific about running dr-exp.

Every path, database URL, interpreter, and concurrency setting flows from a
profile, so no dr-exp module hardcodes a machine-specific value. Profiles ship
as YAML under ``dr_exp.config.machines`` and are addressed by bare name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dr_exp.config.job import ConfigError
from dr_exp.config.names import QUEUE_NAME_BY_ACCELERATOR, Accelerator, QueueName

#: dr-exec's SIGTERM-to-SIGKILL grace window for a training child process.
DEFAULT_TERMINATION_GRACE_SECONDS = 30

#: Directory of the bundled machine profiles shipped inside the package.
BUNDLED_PROFILE_DIR = Path(__file__).resolve().parent / "machines"


class MachineProfile(BaseModel):
    """One host's execution environment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    accelerator: Accelerator
    python_executable: Path
    workspace_root: Path
    run_store_root: Path
    database_url: str
    system_database_url: str
    executor_id: Annotated[str, Field(min_length=1)]
    worker_concurrency: Annotated[int, Field(ge=1)]
    device_env: dict[str, str] = Field(default_factory=dict)
    termination_grace_seconds: Annotated[float, Field(gt=0)] = (
        DEFAULT_TERMINATION_GRACE_SECONDS
    )
    sweep_executor_ids: tuple[str, ...] = ()

    @field_validator("python_executable", "workspace_root", "run_store_root")
    @classmethod
    def _paths_are_absolute(cls, value: Path) -> Path:
        expanded = value.expanduser()
        if not expanded.is_absolute():
            raise ValueError(f"path must be absolute, got {value}")
        return expanded

    @field_validator("executor_id")
    @classmethod
    def _executor_id_is_a_real_name(cls, value: str) -> str:
        """Reject a blank executor id at profile load.

        ``executor_id`` becomes DBOS's executor identity, where a blank value
        fails much later inside ``PlatformDbosConfig`` with a message that names
        neither the profile nor its file. Catching it here keeps the failure
        profile-shaped.
        """
        if not value.strip():
            raise ValueError("executor_id must not be blank")
        return value

    @model_validator(mode="after")
    def _roots_are_distinct(self) -> Self:
        if self.workspace_root == self.run_store_root:
            raise ValueError(
                "workspace_root and run_store_root must be different directories"
            )
        return self

    @model_validator(mode="after")
    def _databases_are_one_database(self) -> Self:
        """Reject a profile that splits the ledger from the DBOS system tables.

        dr-platform's admission and its DBOS enqueue must commit together, so
        the platform tables and the DBOS system schema have to live in one
        database. Nothing downstream checks this, and the failure it produces
        is a confusing partial-commit at runtime, so it is caught here.
        """
        if self.database_url != self.system_database_url:
            raise ValueError(
                "database_url and system_database_url must name the same "
                f"database, got {self.database_url!r} and "
                f"{self.system_database_url!r}"
            )
        return self

    @property
    def queue_name(self) -> QueueName:
        """The DBOS queue this machine's accelerator routes to."""
        return QUEUE_NAME_BY_ACCELERATOR[self.accelerator]

    @property
    def dequeued_queue_names(self) -> tuple[QueueName, ...]:
        """Every queue a worker on this machine must declare and drain.

        ``train-cpu`` is the stage default, so a CPU-labelled job lands there
        regardless of the machine's own accelerator; every worker drains it.
        """
        if self.queue_name is QueueName.TRAIN_CPU:
            return (QueueName.TRAIN_CPU,)
        return (QueueName.TRAIN_CPU, self.queue_name)

    @property
    def sweeping_executor_ids(self) -> frozenset[str]:
        """Executor ids the abandoned-work sweep must treat as live."""
        return frozenset(self.sweep_executor_ids or (self.executor_id,))

    def resolve_device_env(self, device: str) -> dict[str, str]:
        """Render ``device_env`` templates for one device slot."""
        return {
            name: template.format(device=device)
            for name, template in self.device_env.items()
        }

    def workspace_for(self, campaign_key: str, work_key: str) -> Path:
        """Return the working directory shared by one work item's attempts.

        Keyed by ``(campaign_key, work_key)`` rather than by attempt, so a
        checkpoint written by attempt *n* is visible to attempt *n+1* and the
        trainer contract's resume language is actually achievable. The campaign
        is part of the key because ``work_key`` alone repeats across campaigns
        -- the same config submitted twice is deliberately the same work key --
        and two campaigns must not write over each other's artifacts.
        """
        return self.workspace_root / "runs" / campaign_key / work_key


def profile_path(name: str, *, directory: Path | None = None) -> Path:
    """Return the YAML path for a machine profile addressed by name."""
    if "/" in name or name.endswith(".yaml"):
        return Path(name).expanduser()
    return (directory or BUNDLED_PROFILE_DIR) / f"{name}.yaml"


def load_machine_profile(name: str, *, directory: Path | None = None) -> MachineProfile:
    """Load one machine profile by name or explicit path."""
    path = profile_path(name, directory=directory)
    if not path.is_file():
        raise ConfigError(f"machine profile not found: {path}")
    try:
        document = yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise ConfigError(f"{path} is not valid YAML: {error}") from error
    if not isinstance(document, dict):
        raise ConfigError(f"{path} must contain a YAML mapping")
    return MachineProfile.model_validate(document)


__all__ = [
    "BUNDLED_PROFILE_DIR",
    "DEFAULT_TERMINATION_GRACE_SECONDS",
    "MachineProfile",
    "load_machine_profile",
    "profile_path",
]
