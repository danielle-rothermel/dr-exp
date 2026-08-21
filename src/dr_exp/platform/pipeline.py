"""The ``dr-exp-train`` pipeline: one stage that runs one training attempt.

The stage body runs inside dr-platform's preemptible DBOS step, which imposes
three rules it must honour: no DBOS steps or transactions inside it, re-raise
``asyncio.CancelledError`` so operator cancellation is not swallowed, and keep
the return value small because it crosses the step boundary by pickle.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from dr_exec import Executor
from dr_platform import (
    AdmissionPayload,
    LabelQueueRoute,
    PipelineDefinition,
    PipelineIdentity,
    PipelineKey,
    PipelineRegistry,
    StageApplicationFailure,
    StageCompletion,
    StageDefinition,
    StageKey,
    wrap_pipeline_workflows,
)
from sqlalchemy import Engine

from dr_exp.config.machine import MachineProfile
from dr_exp.config.names import (
    PIPELINE_KEY,
    PIPELINE_VERSION,
    STAGE_KEY,
    Accelerator,
    LabelKey,
    QueueName,
)
from dr_exp.execution.attempt import (
    AttemptOutcome,
    AttemptRequest,
    build_executor,
    run_attempt,
)
from dr_exp.execution.cancellation import AttemptCancellationRegistry
from dr_exp.execution.store import load_job_config_reference

#: The pipeline this dr-exp installation submits to and workers drain.
PIPELINE_IDENTITY = PipelineIdentity(PipelineKey(PIPELINE_KEY), PIPELINE_VERSION)

#: The single stage of that pipeline.
TRAIN_STAGE_KEY = StageKey(STAGE_KEY)

#: Enqueue-time routing: an accelerator label picks a dedicated queue, and
#: anything else falls through to the stage default ``train-cpu``.
LABEL_QUEUE_ROUTES = (
    LabelQueueRoute(
        selector={LabelKey.ACCELERATOR.value: Accelerator.CUDA.value},
        queue_name=QueueName.TRAIN_CUDA.value,
    ),
    LabelQueueRoute(
        selector={LabelKey.ACCELERATOR.value: Accelerator.MPS.value},
        queue_name=QueueName.TRAIN_MPS.value,
    ),
)


@dataclass(frozen=True, slots=True)
class StageContext:
    """The machine-specific resources one worker's stage body runs against."""

    profile: MachineProfile
    cancellation: AttemptCancellationRegistry
    engine: Engine
    concurrency: asyncio.Semaphore | None = None


#: Slack added to a profile's termination grace before the stage body stops
#: waiting for dr-exec's teardown. dr-exec's own SIGTERM-to-SIGKILL window is
#: the grace, so this only covers process reaping and run-record finalization.
TEARDOWN_MARGIN_SECONDS = 10.0


def _restore_cancellation_budget() -> None:
    """Let a cancelled stage body await teardown without immediate re-cancel."""
    task = asyncio.current_task()
    if task is None:
        return
    while task.cancelling():
        task.uncancel()


async def _await_teardown(
    attempt_task: asyncio.Task[AttemptOutcome], *, grace_seconds: float
) -> None:
    """Wait out dr-exec's child teardown, bounded by the termination grace.

    The task is shielded because awaiting it from an already-cancelled
    coroutine would otherwise cancel it again immediately. A timeout here
    means dr-exec did not reap the child within its own budget: the stage
    still reports cancellation, since blocking the worker forever is worse
    than a possibly-surviving child. The shield means the timeout leaves the
    attempt task running, so it is cancelled explicitly rather than left
    pending on a loop nobody will await again.
    """
    _restore_cancellation_budget()
    try:
        await asyncio.wait_for(
            asyncio.shield(attempt_task),
            timeout=grace_seconds + TEARDOWN_MARGIN_SECONDS,
        )
    except TimeoutError:
        attempt_task.cancel()
    except Exception:
        return


async def _run_training_attempt(
    context: StageContext,
    payload: AdmissionPayload,
    executor: Executor,
) -> AttemptOutcome:
    config = load_job_config_reference(payload.input_reference, engine=context.engine)
    request = AttemptRequest(
        work_key=payload.work_key.value,
        attempt=payload.attempt_number,
        config=config,
    )
    with context.cancellation.attempt() as token:
        attempt_task = asyncio.create_task(
            run_attempt(
                request,
                profile=context.profile,
                executor=executor,
                cancellation=token,
            )
        )
        try:
            return await asyncio.shield(attempt_task)
        except asyncio.CancelledError:
            # `ProcessExecutor.run` offloads to a thread, so cancelling
            # this coroutine does not touch the child. Signal the token,
            # then wait for dr-exec's own SIGTERM/SIGKILL teardown to
            # finish before letting dr-platform record CANCELLED --
            # otherwise the ledger says CANCELLED while the child runs on.
            token.cancel()
            await _await_teardown(
                attempt_task,
                grace_seconds=context.profile.termination_grace_seconds,
            )
            raise


def build_pipeline(context: StageContext) -> PipelineDefinition:
    """Build the unwrapped pipeline bound to one worker's resources."""
    executor = build_executor(context.profile)

    async def train(payload: AdmissionPayload) -> StageCompletion:
        if context.concurrency is None:
            outcome = await _run_training_attempt(context, payload, executor)
        else:
            async with context.concurrency:
                outcome = await _run_training_attempt(context, payload, executor)
        if outcome.cancelled:
            # dr-exec observed the cancellation and stopped the child. This is
            # not an application failure; dr-platform records CANCELLED.
            raise asyncio.CancelledError
        if not outcome.succeeded:
            raise StageApplicationFailure(
                outcome.require_failure_message(), evidence=outcome.evidence()
            )
        return StageCompletion(output_reference=str(outcome.workspace))

    def args_for(payload: AdmissionPayload) -> tuple[object, ...]:
        return (payload,)

    return PipelineDefinition(
        key=PIPELINE_IDENTITY.key,
        version=PIPELINE_IDENTITY.version,
        stages=(
            StageDefinition(
                key=TRAIN_STAGE_KEY,
                queue_name=QueueName.TRAIN_CPU.value,
                workflow=train,
                args_for=args_for,
                label_queue_routes=LABEL_QUEUE_ROUTES,
            ),
        ),
    )


def build_registry(
    context: StageContext, *, max_recovery_attempts: int
) -> PipelineRegistry:
    """Register the wrapped pipeline; the raw one would never complete."""
    registry = PipelineRegistry()
    registry.register(
        wrap_pipeline_workflows(
            build_pipeline(context),
            max_recovery_attempts=max_recovery_attempts,
        )
    )
    return registry


__all__ = [
    "LABEL_QUEUE_ROUTES",
    "PIPELINE_IDENTITY",
    "TEARDOWN_MARGIN_SECONDS",
    "TRAIN_STAGE_KEY",
    "StageContext",
    "_await_teardown",
    "_restore_cancellation_budget",
    "build_pipeline",
    "build_registry",
]
