"""The pipeline declaration, queue routing, and cancellation fan-out."""

from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from dr_exec import CancelledOutcome, ExitedOutcome, FakeExecutor
from dr_platform import (
    PipelineRegistry,
    StageApplicationFailure,
    resolve_stage_queue_name,
    selector_matches,
)
from sqlalchemy import create_engine

from dr_exp.config.job import JobConfig
from dr_exp.config.machine import MachineProfile
from dr_exp.config.names import (
    PIPELINE_KEY,
    PIPELINE_VERSION,
    STAGE_KEY,
    Accelerator,
    LabelKey,
    QueueName,
)
from dr_exp.execution.cancellation import AttemptCancellationRegistry
from dr_exp.execution.store import reference_for_job_config
from dr_exp.platform import pipeline as pipeline_module
from dr_exp.platform.pipeline import (
    LABEL_QUEUE_ROUTES,
    PIPELINE_IDENTITY,
    TRAIN_STAGE_KEY,
    StageContext,
    _await_teardown,
    build_pipeline,
    build_registry,
)
from dr_exp.platform.registry import submission_registry
from tests.unit.conftest import make_completion as completion


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


@pytest.fixture
def context(profile: MachineProfile) -> StageContext:
    return StageContext(
        profile=profile,
        cancellation=AttemptCancellationRegistry(),
        engine=create_engine(profile.database_url),
    )


def test_pipeline_identity_matches_the_pinned_names() -> None:
    assert PIPELINE_IDENTITY.key.value == PIPELINE_KEY == "dr-exp-train"
    assert PIPELINE_IDENTITY.version == PIPELINE_VERSION == 1
    assert TRAIN_STAGE_KEY.value == STAGE_KEY == "train"


def test_pipeline_declares_exactly_one_stage(context: StageContext) -> None:
    pipeline = build_pipeline(context)
    assert len(pipeline.stages) == 1
    stage = pipeline.stages[0]
    assert stage.key == TRAIN_STAGE_KEY
    assert stage.queue_name == QueueName.TRAIN_CPU.value
    assert pipeline.run_completion is None


@pytest.mark.parametrize(
    ("accelerator", "expected"),
    [
        (Accelerator.CPU, QueueName.TRAIN_CPU),
        (Accelerator.MPS, QueueName.TRAIN_MPS),
        (Accelerator.CUDA, QueueName.TRAIN_CUDA),
    ],
)
def test_labels_route_to_the_accelerator_queue(
    context: StageContext, accelerator: Accelerator, expected: QueueName
) -> None:
    stage = build_pipeline(context).stages[0]
    resolved = resolve_stage_queue_name(
        stage, labels={LabelKey.ACCELERATOR.value: accelerator.value}
    )
    assert resolved == expected.value


def test_unrouted_labels_fall_through_to_the_stage_default(
    context: StageContext,
) -> None:
    stage = build_pipeline(context).stages[0]
    assert (
        resolve_stage_queue_name(stage, labels={"unrelated": "x"})
        == QueueName.TRAIN_CPU.value
    )


def test_label_routes_do_not_overlap() -> None:
    for index, left in enumerate(LABEL_QUEUE_ROUTES):
        for right in LABEL_QUEUE_ROUTES[index + 1 :]:
            assert not selector_matches(left.selector, right.selector)


def test_wrapped_registry_is_accepted_by_the_dispatcher_check(
    context: StageContext,
) -> None:
    from dr_platform.execution.handoff import is_pipeline_wrapped

    registry = build_registry(context, max_recovery_attempts=3)
    assert all(is_pipeline_wrapped(pipeline) for pipeline in registry.pipelines())


def test_submission_registry_is_deliberately_unwrapped() -> None:
    from dr_platform.execution.handoff import is_pipeline_wrapped

    registry = submission_registry()
    assert isinstance(registry, PipelineRegistry)
    assert not any(is_pipeline_wrapped(pipeline) for pipeline in registry.pipelines())


def test_submission_registry_declares_the_same_identity_and_routing() -> None:
    pipeline = submission_registry().get(
        key=PIPELINE_IDENTITY.key, version=PIPELINE_IDENTITY.version
    )
    stage = pipeline.stages[0]
    assert stage.key == TRAIN_STAGE_KEY
    assert stage.queue_name == QueueName.TRAIN_CPU.value
    assert stage.label_queue_routes == LABEL_QUEUE_ROUTES


def admission_payload(reference: str) -> Any:  # noqa: ANN401
    """The dr-platform payload the stage body is invoked with."""
    from dr_platform import AdmissionPayload, CampaignKey, RunKey, StageKey, WorkKey

    return AdmissionPayload(
        campaign_key=CampaignKey(value="unit"),
        work_key=WorkKey(value="abc"),
        work_item_id=1,
        origin_run_key=RunKey(value="run"),
        input_reference=reference,
        labels={LabelKey.ACCELERATOR.value: Accelerator.CPU.value},
        pipeline_key=PIPELINE_KEY,
        pipeline_version=PIPELINE_VERSION,
        stage_key=StageKey(value=STAGE_KEY),
        stage_index=0,
        attempt_number=1,
    )


async def run_stage_body(context: StageContext, *, reference: str) -> None:
    """Invoke the stage body once; the patched executor supplies the outcome."""
    await build_pipeline(context).stages[0].workflow(admission_payload(reference))


@pytest.fixture
def stored_config(monkeypatch: pytest.MonkeyPatch) -> str:
    """A job-config reference the stage body can resolve without a database."""
    config = JobConfig(
        entry_point="dr_exp.training.dummy_trainer:train",
        params={"epochs": 1},
        labels={LabelKey.ACCELERATOR.value: Accelerator.CPU.value},
    )

    def load_fixture(_reference: str, **_kwargs: object) -> JobConfig:
        return config

    monkeypatch.setattr(pipeline_module, "load_job_config_reference", load_fixture)
    return reference_for_job_config(config)


async def test_a_cancelled_dr_exec_outcome_raises_cancelled_error(
    context: StageContext, stored_config: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cancelled attempt is cancelled work, not failed work.

    dr-platform decides the terminal ledger state from what the stage body
    raises: `CancelledError` records CANCELLED, while `StageApplicationFailure`
    records FAILED and puts the item in front of an operator. dr-exec reporting
    a `CancelledOutcome` means the child was torn down on request, so the two
    must not be conflated -- hence the explicit `pytest.raises` on the exact
    type rather than a `not StageApplicationFailure` assertion.
    """
    monkeypatch.setattr(
        pipeline_module,
        "build_executor",
        lambda _profile: FakeExecutor([completion(CancelledOutcome())]),
    )
    with pytest.raises(asyncio.CancelledError):
        await run_stage_body(context, reference=stored_config)


async def test_a_failed_dr_exec_outcome_raises_a_stage_application_failure(
    context: StageContext, stored_config: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other side of that branch: a real failure must still reach FAILED."""
    monkeypatch.setattr(
        pipeline_module,
        "build_executor",
        lambda _profile: FakeExecutor([completion(ExitedOutcome(exit_code=1))]),
    )
    with pytest.raises(StageApplicationFailure):
        await run_stage_body(context, reference=stored_config)


async def test_operator_cancellation_waits_for_teardown(
    context: StageContext, stored_config: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cancelled stage body must call teardown before re-raising."""
    teardown_calls = 0
    release = asyncio.Event()

    async def blocking_run_attempt(*_args: object, **_kwargs: object) -> None:
        await release.wait()

    async def counting_teardown(
        attempt_task: asyncio.Task[object], *, grace_seconds: float
    ) -> None:
        nonlocal teardown_calls
        teardown_calls += 1
        attempt_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await attempt_task

    monkeypatch.setattr(pipeline_module, "run_attempt", blocking_run_attempt)
    monkeypatch.setattr(pipeline_module, "_await_teardown", counting_teardown)

    body = asyncio.create_task(run_stage_body(context, reference=stored_config))
    await asyncio.sleep(0.05)
    body.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await body
    assert teardown_calls == 1


async def test_await_teardown_waits_for_a_shielded_attempt_task() -> None:
    finished = asyncio.Event()

    async def attempt_work() -> None:
        try:
            await asyncio.sleep(0.1)
        finally:
            finished.set()

    attempt_task = asyncio.create_task(attempt_work())
    await asyncio.sleep(0.02)

    async def cancelled_caller() -> None:
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        await _await_teardown(attempt_task, grace_seconds=1.0)

    caller = asyncio.create_task(cancelled_caller())
    with pytest.raises(asyncio.CancelledError):
        await caller
    await asyncio.wait_for(finished.wait(), timeout=1)
    assert finished.is_set()


async def test_concurrency_gate_limits_parallel_stage_bodies(
    profile: MachineProfile, stored_config: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = asyncio.Semaphore(1)
    context = StageContext(
        profile=profile,
        cancellation=AttemptCancellationRegistry(),
        engine=create_engine(profile.database_url),
        concurrency=gate,
    )
    in_flight = 0
    peak = 0
    original_run_attempt = pipeline_module.run_attempt

    async def slow_run_attempt(*args: object, **kwargs: object) -> object:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        try:
            return await original_run_attempt(*args, **kwargs)
        finally:
            in_flight -= 1

    monkeypatch.setattr(
        pipeline_module,
        "build_executor",
        lambda _profile: FakeExecutor(
            [
                completion(ExitedOutcome(exit_code=0), payload={"ok": True}),
                completion(ExitedOutcome(exit_code=0), payload={"ok": True}),
            ]
        ),
    )
    monkeypatch.setattr(pipeline_module, "run_attempt", slow_run_attempt)

    await asyncio.gather(
        run_stage_body(context, reference=stored_config),
        run_stage_body(context, reference=stored_config),
    )
    assert peak == 1


def test_registry_cancels_registered_attempts() -> None:
    registry = AttemptCancellationRegistry()
    with registry.attempt() as token:
        assert not token.cancelled
        registry.cancel_all()
        assert token.cancelled
    assert registry.process_token.cancelled


def test_attempts_registered_after_shutdown_start_cancelled() -> None:
    registry = AttemptCancellationRegistry()
    registry.cancel_all()
    with registry.attempt() as token:
        assert token.cancelled
    assert registry.shutting_down


def test_completed_attempts_are_deregistered() -> None:
    registry = AttemptCancellationRegistry()
    with registry.attempt() as finished:
        pass
    registry.cancel_all()
    assert not finished.cancelled


def test_concurrent_attempts_are_all_cancelled() -> None:
    registry = AttemptCancellationRegistry()
    entered = threading.Barrier(4)
    released = threading.Event()
    observed: list[bool] = []

    def hold() -> None:
        with registry.attempt() as token:
            entered.wait(timeout=5)
            released.wait(timeout=5)
            observed.append(token.cancelled)

    threads = [threading.Thread(target=hold) for _ in range(3)]
    for thread in threads:
        thread.start()
    entered.wait(timeout=5)
    registry.cancel_all()
    released.set()
    for thread in threads:
        thread.join(timeout=5)
    assert observed == [True, True, True]


def test_registry_is_idle_when_no_attempt_is_registered() -> None:
    registry = AttemptCancellationRegistry()
    assert registry.in_flight == 0
    assert registry.wait_for_idle(timeout=0)


def test_wait_for_idle_blocks_while_an_attempt_is_in_flight() -> None:
    """Worker shutdown joins on this before destroying its DBOS runtime.

    The wait is released by the attempt deregistering, not by elapsed time:
    the release event below is what unblocks it.
    """
    registry = AttemptCancellationRegistry()
    entered = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with registry.attempt():
            entered.set()
            release.wait(timeout=5)

    thread = threading.Thread(target=hold)
    thread.start()
    assert entered.wait(timeout=5)
    assert registry.in_flight == 1
    assert not registry.wait_for_idle(timeout=0)

    release.set()
    assert registry.wait_for_idle(timeout=5)
    assert registry.in_flight == 0
    thread.join(timeout=5)
