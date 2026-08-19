"""Bounded and unbounded worker drain loops.

A worker's actual work happens on DBOS queue-listener threads, so the main
thread's only job is to decide when to stop. Both loops below synchronize on
ledger state rather than elapsed time: ``--max-jobs`` waits for that many work
items to reach a terminal state, and the unbounded loop waits for a signal.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from dr_platform import StageExecutionState, list_work_items
from sqlalchemy import Engine

from dr_exp.execution.cancellation import AttemptCancellationRegistry

#: States a work item never leaves.
TERMINAL_STATES = frozenset(
    {
        StageExecutionState.SUCCEEDED,
        StageExecutionState.FAILED,
        StageExecutionState.CANCELLED,
    }
)

#: How often a bounded drain re-reads the ledger. Latency here adds to a
#: worker's exit time only, never to job throughput.
POLL_INTERVAL_SECONDS = 0.25


@dataclass(frozen=True, slots=True)
class DrainSummary:
    """What a drain loop observed before returning."""

    terminal_count: int
    reached_limit: bool
    interrupted: bool


def count_terminal_work_items(engine: Engine, *, campaign_key: str) -> int:
    """Count work items of one campaign that have reached a terminal state."""
    return sum(
        1
        for item in list_work_items(campaign_key, engine=engine)
        if item.state in TERMINAL_STATES
    )


def drain_until(
    *,
    engine: Engine,
    campaign_key: str,
    cancellation: AttemptCancellationRegistry,
    max_jobs: int | None,
    deadline_seconds: float | None = None,
) -> DrainSummary:
    """Block until ``max_jobs`` items are terminal, or until interrupted.

    With ``max_jobs=None`` this waits for a shutdown signal. ``deadline_seconds``
    is a watchdog for tests and smoke runs: reaching it is a failure to make
    progress, not a success condition.
    """
    stop = threading.Event()
    elapsed = 0.0
    terminal = 0
    while True:
        if cancellation.shutting_down:
            return DrainSummary(
                terminal_count=terminal, reached_limit=False, interrupted=True
            )
        if max_jobs is not None:
            terminal = count_terminal_work_items(engine, campaign_key=campaign_key)
            if terminal >= max_jobs:
                return DrainSummary(
                    terminal_count=terminal,
                    reached_limit=True,
                    interrupted=False,
                )
        if deadline_seconds is not None and elapsed >= deadline_seconds:
            return DrainSummary(
                terminal_count=terminal,
                reached_limit=False,
                interrupted=False,
            )
        stop.wait(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS


__all__ = [
    "POLL_INTERVAL_SECONDS",
    "TERMINAL_STATES",
    "DrainSummary",
    "count_terminal_work_items",
    "drain_until",
]
