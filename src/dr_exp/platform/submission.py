"""Submitting jobs and sweeps into the dr-platform ledger."""

from __future__ import annotations

from dataclasses import dataclass

from dr_platform import (
    PipelineRegistry,
    RegistrationClosureError,
    RunMemberInput,
    RunRegistrationDeclaration,
    SubmissionReceipt,
    WorkInput,
    list_run_members,
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
        validate_entry_point_importable(
            config, python_executable=profile.python_executable
        )

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
                    input_reference=store_job_config(config, engine=engine),
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
    submitted = tuple(member.work.work_key.value for member in members)
    _require_membership_registered(
        submitted, run_key=receipt.run_key.value, engine=engine
    )
    return SubmissionResult(receipt=receipt, work_keys=submitted)


#: How many run members to read per page when verifying a submission landed.
#: dr-platform's readers are bounded and cursor-paged, so a sweep larger than
#: one page must be walked rather than truncated -- a truncated read would
#: report the tail of a perfectly good submission as discarded.
_MEMBERSHIP_PAGE_SIZE = 1000


def _registered_work_keys(run_key: str, *, engine: Engine) -> frozenset[str]:
    """Every work key recorded as a member of ``run_key``, across all pages."""
    keys: set[str] = set()
    cursor: int | None = None
    while True:
        page = list_run_members(
            run_key, engine=engine, cursor=cursor, limit=_MEMBERSHIP_PAGE_SIZE
        )
        if not page:
            return frozenset(keys)
        keys.update(member.work_key.value for member in page)
        cursor = page[-1].member_ordinal


def _require_membership_registered(
    submitted: tuple[str, ...], *, run_key: str, engine: Engine
) -> None:
    """Refuse to report success for a submission the run discarded.

    A run's membership is immutable once registration closes, and dr-platform
    resolves a second ``submit`` under a closed run key as an idempotent replay:
    it returns the *stored* receipt and registers nothing. That is correct for
    an identical replay, but for a different membership it silently drops the
    work, and the stored receipt describes the original registration, so
    echoing it reads as a successful new submission.

    dr-platform raises ``PipelineRunConflictError`` only when the run's
    immutable provenance differs, and ``expected_member_count`` is the only
    part of that provenance a differing membership changes -- so two submits of
    one config each conflict on nothing and produce exactly this misreport.
    Reading the recorded membership back is what distinguishes the two cases.
    """
    registered = _registered_work_keys(run_key, engine=engine)
    discarded = [key for key in submitted if key not in registered]
    if not discarded:
        return
    listed = ", ".join(key[:12] for key in discarded)
    raise RegistrationClosureError(
        f"run {run_key!r} is already closed, so this submission registered "
        f"nothing: {len(discarded)} of {len(submitted)} configuration(s) were "
        f"discarded ({listed}). A run's membership is fixed when it closes. "
        f"Submit these configurations under a different --run key."
    )


__all__ = ["SubmissionResult", "submit_jobs"]
