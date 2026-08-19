"""Pipeline registries for callers that do not execute work.

``submit`` consults the registry only for the pipeline's identity, stage keys,
and queue routing, so a client that never runs a stage does not need a machine
profile or a process executor. Workers build the real, wrapped registry through
``dr_exp.platform.pipeline.build_registry``.
"""

from __future__ import annotations

from dr_platform import (
    AdmissionPayload,
    PipelineDefinition,
    PipelineRegistry,
    StageCompletion,
    StageDefinition,
)

from dr_exp.config.names import QueueName
from dr_exp.platform.pipeline import (
    LABEL_QUEUE_ROUTES,
    PIPELINE_IDENTITY,
    TRAIN_STAGE_KEY,
)


async def _unrunnable_stage(_payload: AdmissionPayload) -> StageCompletion:
    raise RuntimeError(
        "the submission registry cannot run stages; start a worker with "
        "'dr_exp worker --machine <profile>'"
    )


def _args_for(payload: AdmissionPayload) -> tuple[object, ...]:
    return (payload,)


def submission_registry() -> PipelineRegistry:
    """Return a registry sufficient for submission and inspection only.

    It is deliberately unwrapped: ``register_scheduled_dispatcher`` rejects an
    unwrapped pipeline, so this registry cannot be mistaken for a worker's.
    """
    registry = PipelineRegistry()
    registry.register(
        PipelineDefinition(
            key=PIPELINE_IDENTITY.key,
            version=PIPELINE_IDENTITY.version,
            stages=(
                StageDefinition(
                    key=TRAIN_STAGE_KEY,
                    queue_name=QueueName.TRAIN_CPU.value,
                    workflow=_unrunnable_stage,
                    args_for=_args_for,
                    label_queue_routes=LABEL_QUEUE_ROUTES,
                ),
            ),
        )
    )
    return registry


__all__ = ["submission_registry"]
