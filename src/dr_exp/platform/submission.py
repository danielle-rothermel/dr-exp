"""Submitting jobs and sweeps into the dr-platform ledger."""

from __future__ import annotations

from dataclasses import dataclass

from dr_platform import (
    PipelineRegistry,
    RunMemberInput,
    RunRegistrationDeclaration,
    SubmissionReceipt,
    WorkInput,
    submit,
)
from sqlalchemy import Engine

from dr_exp.config.identity import execution_config_reference, work_key
from dr_exp.config.job import JobConfig, validate_entry_point_importable
from dr_exp.config.machine import MachineProfile
from dr_exp.execution.store import store_job_config
from dr_exp.platform.pipeline import PIPELINE_IDENTITY
from dr_exp.platform.registry import submission_registry


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    """A completed submission and the work keys it registered."""

    receipt: SubmissionReceipt
    work_keys: tuple[str, ...]


def submit_jobs(
    configs: tuple[JobConfig, ...],
    *,
    campaign_key: str,
    run_key: str,
    profile: MachineProfile,
    engine: Engine,
    registry: PipelineRegistry | None = None,
) -> SubmissionResult:
    """Register ``configs`` as one run of the ``dr-exp-train`` pipeline.

    Configurations that hash to the same work key are one unit of work: the
    duplicate is dropped locally, and a work key already present in the
    campaign is reused by dr-platform rather than recomputed.
    """
    if not configs:
        raise ValueError("submission requires at least one job configuration")
    for config in configs:
        validate_entry_point_importable(config)

    members: list[RunMemberInput] = []
    seen: set[str] = set()
    for config in configs:
        key = work_key(config)
        if key in seen:
            continue
        seen.add(key)
        members.append(
            RunMemberInput(
                ordinal=len(members),
                work=WorkInput(
                    work_key=key,
                    input_reference=store_job_config(
                        config,
                        work_key=key,
                        workspace_root=profile.workspace_root,
                    ),
                    labels=dict(config.labels),
                    priority=config.priority,
                ),
            )
        )

    receipt = submit(
        campaign_key=campaign_key,
        run_key=run_key,
        pipeline=PIPELINE_IDENTITY,
        execution_config_reference=execution_config_reference(),
        declaration=RunRegistrationDeclaration(expected_member_count=len(members)),
        members=members,
        registry=registry if registry is not None else submission_registry(),
        engine=engine,
    )
    return SubmissionResult(
        receipt=receipt,
        work_keys=tuple(member.work.work_key.value for member in members),
    )


__all__ = ["SubmissionResult", "submit_jobs"]
