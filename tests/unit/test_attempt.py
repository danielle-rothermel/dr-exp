"""Building and interpreting one training attempt, without spawning one."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from dr_exec import (
    CancelToken,
    CancelledOutcome,
    EnvGrantKind,
    ExitedOutcome,
    FakeExecutor,
    LimitKind,
    TrustedPythonTarget,
    WorkingDirectoryGrantKind,
)

from dr_exp.config.job import Budgets, JobConfig
from dr_exp.config.machine import MachineProfile
from dr_exp.execution.attempt import (
    RESULT_FILENAME,
    AttemptRequest,
    build_execution_job,
    build_trainer_request,
    run_attempt,
)
from tests.unit.conftest import make_completion

CONFIG = JobConfig(
    entry_point="dr_exp.training.dummy_trainer:train",
    params={"epochs": 2},
    labels={"accelerator": "cpu"},
)


@pytest.fixture
def profile(tmp_path: Path) -> MachineProfile:
    return MachineProfile.model_validate(
        {
            "name": "test",
            "accelerator": "cpu",
            "python_executable": sys.executable,
            "workspace_root": tmp_path / "workspace",
            "run_store_root": tmp_path / "runs",
            "database_url": "postgresql+psycopg:///dr_exp_test",
            "system_database_url": "postgresql+psycopg:///dr_exp_test",
            "executor_id": "test-0",
            "worker_concurrency": 1,
        }
    )


def test_trainer_request_carries_the_documented_fields(
    profile: MachineProfile,
) -> None:
    request = AttemptRequest(work_key="abc", attempt=3, config=CONFIG)
    workspace = request.workspace(profile)
    assert build_trainer_request(request, workspace=workspace) == {
        "params": {"epochs": 2},
        "workspace": str(workspace),
        "work_key": "abc",
        "attempt": 3,
    }


def test_execution_job_grants_the_attempt_workspace(
    profile: MachineProfile,
) -> None:
    request = AttemptRequest(work_key="abc", attempt=1, config=CONFIG)
    workspace = request.workspace(profile)
    workspace.mkdir(parents=True)
    job = build_execution_job(request, profile=profile, workspace=workspace)
    assert job.workspace.kind is WorkingDirectoryGrantKind.CALLER
    assert job.workspace.path == workspace


def test_execution_job_targets_the_configured_entry_point(
    profile: MachineProfile,
) -> None:
    request = AttemptRequest(work_key="abc", attempt=1, config=CONFIG)
    workspace = request.workspace(profile)
    workspace.mkdir(parents=True)
    job = build_execution_job(request, profile=profile, workspace=workspace)
    assert isinstance(job.target, TrustedPythonTarget)
    assert "dr_exp.training.dummy_trainer" in job.target.driver_source
    assert "'train'" in job.target.driver_source


def test_execution_job_overlays_the_profile_device_env(
    tmp_path: Path, profile: MachineProfile
) -> None:
    cuda_profile = profile.model_copy(
        update={"device_env": {"CUDA_VISIBLE_DEVICES": "{device}"}}
    )
    request = AttemptRequest(work_key="abc", attempt=1, config=CONFIG)
    workspace = request.workspace(cuda_profile)
    workspace.mkdir(parents=True)
    job = build_execution_job(request, profile=cuda_profile, workspace=workspace)
    assert job.env.kind is EnvGrantKind.OVERLAY
    granted = {variable.name: variable.value for variable in job.env.variables}
    assert granted["CUDA_VISIBLE_DEVICES"] == "0"


def test_execution_job_is_unbudgeted_without_declared_budgets(
    profile: MachineProfile,
) -> None:
    request = AttemptRequest(work_key="abc", attempt=1, config=CONFIG)
    workspace = request.workspace(profile)
    workspace.mkdir(parents=True)
    job = build_execution_job(request, profile=profile, workspace=workspace)
    assert job.budgets.wall_time.kind is LimitKind.UNBUDGETED


def test_execution_job_converts_a_wall_time_budget_to_nanoseconds(
    profile: MachineProfile,
) -> None:
    budgeted = CONFIG.model_copy(update={"budgets": Budgets(wall_time_seconds=1.5)})
    request = AttemptRequest(work_key="abc", attempt=1, config=budgeted)
    workspace = request.workspace(profile)
    workspace.mkdir(parents=True)
    job = build_execution_job(request, profile=profile, workspace=workspace)
    assert job.budgets.wall_time.limit == 1_500_000_000


def test_each_attempt_mints_a_distinct_job_id(
    profile: MachineProfile,
) -> None:
    request = AttemptRequest(work_key="abc", attempt=1, config=CONFIG)
    workspace = request.workspace(profile)
    workspace.mkdir(parents=True)
    first = build_execution_job(request, profile=profile, workspace=workspace)
    second = build_execution_job(request, profile=profile, workspace=workspace)
    assert first.job_id != second.job_id


async def test_successful_attempt_writes_its_result(
    profile: MachineProfile,
) -> None:
    executor = FakeExecutor(
        [make_completion(ExitedOutcome(exit_code=0), payload={"loss": 0.5})]
    )
    request = AttemptRequest(work_key="abc", attempt=1, config=CONFIG)
    outcome = await run_attempt(
        request,
        profile=profile,
        executor=executor,
        cancellation=CancelToken(),
    )
    assert outcome.succeeded
    assert outcome.result == {"loss": 0.5}
    written = json.loads((outcome.workspace / RESULT_FILENAME).read_text())
    assert written == {"loss": 0.5}


async def test_nonzero_exit_is_reported_as_a_failure(
    profile: MachineProfile,
) -> None:
    executor = FakeExecutor([make_completion(ExitedOutcome(exit_code=1))])
    outcome = await run_attempt(
        AttemptRequest(work_key="abc", attempt=1, config=CONFIG),
        profile=profile,
        executor=executor,
        cancellation=CancelToken(),
    )
    assert not outcome.succeeded
    assert outcome.failure_message is not None
    assert "exited with code 1" in outcome.failure_message
    assert not (outcome.workspace / RESULT_FILENAME).exists()


async def test_cancelled_attempt_is_reported_as_cancelled(
    profile: MachineProfile,
) -> None:
    executor = FakeExecutor([make_completion(CancelledOutcome())])
    outcome = await run_attempt(
        AttemptRequest(work_key="abc", attempt=1, config=CONFIG),
        profile=profile,
        executor=executor,
        cancellation=CancelToken(),
    )
    assert outcome.cancelled
    assert not outcome.succeeded


async def test_failure_evidence_is_strict_json(
    profile: MachineProfile,
) -> None:
    from dr_serialize import validate_strict_json

    executor = FakeExecutor([make_completion(ExitedOutcome(exit_code=2))])
    outcome = await run_attempt(
        AttemptRequest(work_key="abc", attempt=1, config=CONFIG),
        profile=profile,
        executor=executor,
        cancellation=CancelToken(),
    )
    evidence: Any = outcome.evidence()
    validate_strict_json(evidence)
    assert evidence["outcome"]["kind"] == "exited"
    assert evidence["attribution"]["owner"] == "payload"
    assert evidence["workspace"] == str(outcome.workspace)


async def test_attempt_creates_its_workspace(
    profile: MachineProfile,
) -> None:
    executor = FakeExecutor([make_completion(ExitedOutcome(exit_code=0), payload={})])
    request = AttemptRequest(work_key="abc", attempt=4, config=CONFIG)
    assert not request.workspace(profile).exists()
    outcome = await run_attempt(
        request,
        profile=profile,
        executor=executor,
        cancellation=CancelToken(),
    )
    assert outcome.workspace.is_dir()
    assert outcome.workspace == profile.workspace_for("abc", 4)
