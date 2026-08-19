"""The pipeline declaration, queue routing, and cancellation fan-out."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest
from dr_platform import (
    PipelineRegistry,
    resolve_stage_queue_name,
    selector_matches,
)

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
from dr_exp.platform.pipeline import (
    LABEL_QUEUE_ROUTES,
    PIPELINE_IDENTITY,
    TRAIN_STAGE_KEY,
    StageContext,
    build_pipeline,
    build_registry,
)
from dr_exp.platform.registry import submission_registry


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
    return StageContext(profile=profile, cancellation=AttemptCancellationRegistry())


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
