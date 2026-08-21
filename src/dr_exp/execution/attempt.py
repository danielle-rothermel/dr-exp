"""Running one training attempt as an isolated child process.

This module owns the translation from a dr-platform work item to a dr-exec
``ExecutionJob`` and back. It is deliberately free of DBOS: the stage body in
``dr_exp.platform.stage`` supplies cancellation and interprets the outcome.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from dr_exec import (
    Budgets,
    CancelledOutcome,
    CancelToken,
    CompletedExecution,
    DirectoryRunStore,
    EnvGrant,
    ExecutionJob,
    Executor,
    ExecutorSelfBudgets,
    ExitedOutcome,
    FiniteDurationLimit,
    ImportableEntryPoint,
    ImportableJsonResultError,
    IsolatedHostPythonRuntime,
    JobId,
    ProcessExecutor,
    WorkingDirectoryGrant,
    build_trusted_importable_json_job,
    parse_importable_json_result,
)
from dr_serialize import Jsonable

from dr_exp.config.job import JobConfig
from dr_exp.config.machine import MachineProfile
from dr_exp.config.names import RequestField

#: Name of the trainer's JSON result written into the attempt workspace.
RESULT_FILENAME = "result.json"

#: Device slot rendered into ``MachineProfile.device_env`` templates. Local
#: profiles address a single accelerator; the cluster phase will thread a real
#: per-worker slot through here.
DEFAULT_DEVICE_SLOT = "0"


@dataclass(frozen=True, slots=True)
class AttemptRequest:
    """Everything one attempt needs, independent of dr-platform types."""

    campaign_key: str
    work_key: str
    attempt: int
    config: JobConfig

    def workspace(self, profile: MachineProfile) -> Path:
        """The working directory this work item's attempts share on ``profile``.

        ``attempt`` still identifies the attempt in the trainer request and in
        the ledger; it does not select a directory, so a checkpoint survives
        into the next attempt.
        """
        return profile.workspace_for(self.campaign_key, self.work_key)


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    """The result of one attempt, successful or not."""

    completed: CompletedExecution
    workspace: Path
    result: Jsonable | None
    failure_message: str | None

    @property
    def succeeded(self) -> bool:
        """Whether the trainer exited cleanly and returned a JSON result."""
        return self.failure_message is None

    @property
    def cancelled(self) -> bool:
        """Whether the attempt ended because it was cancelled.

        The stage body branches on this to raise ``CancelledError`` instead of
        an application failure, so it reads dr-exec's typed outcome rather
        than matching on a string.
        """
        return isinstance(self.completed.result.outcome, CancelledOutcome)

    def require_failure_message(self) -> str:
        """Return the failure message, refusing to describe a success.

        The caller reaches this only after checking :attr:`succeeded`, but an
        explicit raise keeps that contract enforced under ``python -O``, where
        an assertion would vanish.
        """
        if self.failure_message is None:
            raise ValueError("attempt succeeded; there is no failure message")
        return self.failure_message

    def evidence(self) -> Jsonable:
        """A strict-JSON record of this attempt for failure evidence."""
        result = self.completed.result
        return {
            "outcome": result.outcome.model_dump(mode="json"),
            "attribution": result.attribution.model_dump(mode="json"),
            "record": self.completed.record_receipt.model_dump(mode="json"),
            "workspace": str(self.workspace),
        }


def build_trainer_request(
    request: AttemptRequest, *, workspace: Path
) -> dict[str, Jsonable]:
    """Build the strict-JSON payload handed to the trainer callable."""
    return {
        RequestField.PARAMS: dict(request.config.params),
        RequestField.WORKSPACE: str(workspace),
        RequestField.WORK_KEY: request.work_key,
        RequestField.ATTEMPT: request.attempt,
    }


def build_execution_job(
    request: AttemptRequest,
    *,
    profile: MachineProfile,
    workspace: Path,
    job_id: JobId | None = None,
) -> ExecutionJob:
    """Build the dr-exec job for one attempt.

    A fresh ``JobId`` is minted per attempt: dr-exec derives its run-record
    directory deterministically from the job id, so reusing one would collide.
    """
    module_name, attribute_name = request.config.entry_point_parts
    budgets = Budgets()
    if request.config.budgets is not None:
        wall_time_seconds = request.config.budgets.wall_time_seconds
        if wall_time_seconds is not None:
            budgets = Budgets(
                wall_time=FiniteDurationLimit.from_seconds(wall_time_seconds)
            )
    job = build_trusted_importable_json_job(
        job_id if job_id is not None else JobId(uuid.uuid4()),
        ImportableEntryPoint(module_name=module_name, attribute_name=attribute_name),
        build_trainer_request(request, workspace=workspace),
        # `overlay` snapshots the worker's own environment and layers the
        # device variables on top, so a training child inherits everything the
        # worker was started with. That is what a local trainer needs (HF
        # caches, tokens, proxies) but it is not a sandbox; a profile-level
        # exclusion list belongs here if untrusted trainers ever run.
        env=EnvGrant.overlay(profile.resolve_device_env(DEFAULT_DEVICE_SLOT)),
        budgets=budgets,
    )
    # The builder always grants a scratch directory; an attempt needs its own
    # durable workspace so checkpoints and artifacts survive the run.
    return dataclasses.replace(job, workspace=WorkingDirectoryGrant.caller(workspace))


def build_executor(profile: MachineProfile) -> ProcessExecutor:
    """Build the executor that runs attempts on ``profile``.

    ``DirectoryRunStore`` does not create its root, so the caller-visible
    failure mode of a missing directory is resolved here instead.
    """
    profile.run_store_root.mkdir(parents=True, exist_ok=True)
    return ProcessExecutor(
        runtime=IsolatedHostPythonRuntime(executable=profile.python_executable),
        run_store=DirectoryRunStore(root=profile.run_store_root),
        self_budgets=ExecutorSelfBudgets(
            termination_time=FiniteDurationLimit.from_seconds(
                profile.termination_grace_seconds
            )
        ),
    )


async def run_attempt(
    request: AttemptRequest,
    *,
    profile: MachineProfile,
    executor: Executor,
    cancellation: CancelToken,
) -> AttemptOutcome:
    """Run one attempt to completion and interpret its outcome.

    Never raises for a payload failure: a non-success outcome is reported in
    ``AttemptOutcome.failure_message`` so the caller owns the ledger decision.
    """
    workspace = request.workspace(profile)
    workspace.mkdir(parents=True, exist_ok=True)
    job = build_execution_job(request, profile=profile, workspace=workspace)
    completed = await executor.run(job, cancellation=cancellation)

    try:
        result = parse_importable_json_result(completed)
    except ImportableJsonResultError as error:
        return AttemptOutcome(
            completed=completed,
            workspace=workspace,
            result=None,
            failure_message=_failure_message(completed, error),
        )

    (workspace / RESULT_FILENAME).write_text(
        json.dumps(result, indent=2, sort_keys=True)
    )
    return AttemptOutcome(
        completed=completed,
        workspace=workspace,
        result=result,
        failure_message=None,
    )


def _failure_message(
    completed: CompletedExecution, error: ImportableJsonResultError
) -> str:
    outcome = completed.result.outcome
    attribution = completed.result.attribution
    detail = attribution.detail or str(error)
    if isinstance(outcome, ExitedOutcome):
        return (
            f"training attempt exited with code {outcome.exit_code} "
            f"({attribution.owner.value}): {detail}"
        )
    return (
        f"training attempt ended as {outcome.kind.value} "
        f"({attribution.owner.value}): {detail}"
    )


__all__ = [
    "DEFAULT_DEVICE_SLOT",
    "RESULT_FILENAME",
    "AttemptOutcome",
    "AttemptRequest",
    "build_execution_job",
    "build_executor",
    "build_trainer_request",
    "run_attempt",
]
