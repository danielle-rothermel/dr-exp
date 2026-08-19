"""The ``dr-exp-train`` pipeline: one stage that runs one training attempt.

The stage body runs inside dr-platform's preemptible DBOS step, which imposes
three rules it must honour: no DBOS steps or transactions inside it, re-raise
``asyncio.CancelledError`` so operator cancellation is not swallowed, and keep
the return value small because it crosses the step boundary by pickle.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

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


def build_pipeline(context: StageContext) -> PipelineDefinition:
    """Build the unwrapped pipeline bound to one worker's resources."""
    executor = build_executor(context.profile)

    async def train(payload: AdmissionPayload) -> StageCompletion:
        config = load_job_config_reference(payload.input_reference)
        request = AttemptRequest(
            work_key=payload.work_key.value,
            attempt=payload.attempt_number,
            config=config,
        )
        with context.cancellation.attempt() as token:
            try:
                outcome = await run_attempt(
                    request,
                    profile=context.profile,
                    executor=executor,
                    cancellation=token,
                )
            except asyncio.CancelledError:
                # Tear the child down, then let dr-platform record CANCELLED.
                token.cancel()
                raise
        if not outcome.succeeded:
            assert outcome.failure_message is not None
            raise StageApplicationFailure(
                outcome.failure_message, evidence=outcome.evidence()
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
    "TRAIN_STAGE_KEY",
    "StageContext",
    "build_pipeline",
    "build_registry",
]
