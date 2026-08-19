"""Helpers shared by the unit suite.

The scripted-completion builder lives here because two modules need it: the
attempt tests interpret dr-exec outcomes directly, and the pipeline tests drive
the stage body against them to pin the ledger state each one produces.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from dr_exec import (
    CompletedExecution,
    ExecutionAttribution,
    ExecutionId,
    ExecutionMeasurements,
    ExecutionOutcome,
    ExecutionResult,
    ExitedOutcome,
    FailureOwner,
    FakeRecordReceipt,
    JobId,
    PayloadOutputs,
    RetainedPayloadStream,
)
from dr_exec.importable_json import ENVELOPE_SCHEMA, ENVELOPE_SCHEMA_VERSION
from dr_exec.recording.references import attempt_id_for_job
from dr_serialize import Jsonable, build_identity_document


def make_completion(
    outcome: ExecutionOutcome, *, payload: Jsonable | None = None
) -> CompletedExecution:
    """Build a scripted completion a ``FakeExecutor`` will accept."""
    job_id = JobId(uuid.uuid4())
    execution_id = ExecutionId(job_id=job_id, attempt_id=attempt_id_for_job(job_id))
    now = datetime.now(UTC)
    empty = RetainedPayloadStream(head=b"", tail=b"", produced_bytes=0, dropped_bytes=0)
    outputs = (
        ()
        if payload is None
        else (
            build_identity_document(
                schema=ENVELOPE_SCHEMA,
                schema_version=ENVELOPE_SCHEMA_VERSION,
                payload=payload,
            ),
        )
    )
    owner = (
        FailureOwner.NONE
        if isinstance(outcome, ExitedOutcome) and outcome.exit_code == 0
        else FailureOwner.PAYLOAD
    )
    return CompletedExecution(
        result=ExecutionResult(
            execution_id=execution_id,
            outcome=outcome,
            attribution=ExecutionAttribution(owner=owner),
            protocol_outputs=outputs,
            payload_outputs=PayloadOutputs(stdout=empty, stderr=empty),
            measurements=ExecutionMeasurements(
                started_at=now,
                finished_at=now,
                duration_ns=0,
                teardown_duration_ns=0,
                input_bytes=0,
                protocol_bytes_received=0,
            ),
        ),
        record_receipt=FakeRecordReceipt(execution_id=execution_id),
    )


__all__ = ["make_completion"]
