"""``--max-jobs`` counts what this drain finished, not what the campaign holds.

A campaign accumulates terminal work across runs. If the bounded drain counted
every terminal item it saw, a second smoke run against the same campaign would
satisfy its limit on the first poll and exit before running anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from dr_platform import StageExecutionState

from dr_exp.execution.cancellation import AttemptCancellationRegistry
from dr_exp.platform import drain as drain_module
from dr_exp.platform.drain import drain_until

CAMPAIGN = "unit"


@dataclass(frozen=True)
class FakeKey:
    """Stands in for dr-platform's work-key wrapper."""

    value: str


@dataclass(frozen=True)
class FakeItem:
    """The only two fields of a work item the drain loop reads."""

    work_key: FakeKey
    state: StageExecutionState


def item(key: str, state: StageExecutionState) -> FakeItem:
    return FakeItem(work_key=FakeKey(key), state=state)


@pytest.fixture
def ledger(monkeypatch: pytest.MonkeyPatch) -> list[list[FakeItem]]:
    """A scripted ledger: one entry per ``list_work_items`` call.

    The last entry repeats, so a drain that keeps polling sees a stable world
    instead of running off the end.
    """
    polls: list[list[FakeItem]] = []

    def fake_list_work_items(campaign_key: str, *, engine: Any) -> list[FakeItem]:  # noqa: ANN401
        return polls[0] if len(polls) == 1 else polls.pop(0)

    monkeypatch.setattr(drain_module, "list_work_items", fake_list_work_items)
    return polls


def drain(max_jobs: int | None, **kwargs: Any) -> Any:  # noqa: ANN401
    return drain_until(
        engine=object(),
        campaign_key=CAMPAIGN,
        cancellation=AttemptCancellationRegistry(),
        max_jobs=max_jobs,
        **kwargs,
    )


def test_pre_existing_terminal_work_does_not_satisfy_the_limit(
    ledger: list[list[FakeItem]],
) -> None:
    """Two items already finished; the drain must still wait for a new one."""
    settled = [
        item("old-a", StageExecutionState.SUCCEEDED),
        item("old-b", StageExecutionState.SUCCEEDED),
    ]
    ledger.extend(
        [
            settled,  # snapshot at drain start
            settled,  # nothing new yet
            [*settled, item("new", StageExecutionState.SUCCEEDED)],
        ]
    )

    summary = drain(1, deadline_seconds=5)

    assert summary.reached_limit
    assert summary.terminal_count == 1


def test_the_limit_counts_only_items_that_finished_during_the_drain(
    ledger: list[list[FakeItem]],
) -> None:
    running = [item("a", StageExecutionState.ADMITTED)]
    ledger.extend(
        [
            running,
            [item("a", StageExecutionState.SUCCEEDED)],
            [
                item("a", StageExecutionState.SUCCEEDED),
                item("b", StageExecutionState.FAILED),
            ],
        ]
    )

    summary = drain(2, deadline_seconds=5)

    assert summary.reached_limit
    assert summary.terminal_count == 2


def test_a_cancelled_item_counts_toward_the_limit(
    ledger: list[list[FakeItem]],
) -> None:
    ledger.extend(
        [
            [item("a", StageExecutionState.ADMITTED)],
            [item("a", StageExecutionState.CANCELLED)],
        ]
    )

    summary = drain(1, deadline_seconds=5)

    assert summary.reached_limit
    assert summary.terminal_count == 1


def test_explicit_baseline_counts_a_key_that_finishes_during_startup(
    ledger: list[list[FakeItem]],
) -> None:
    """A pre-captured baseline must not hide fast completions during launch."""
    settled = [item("fast", StageExecutionState.SUCCEEDED)]
    ledger.extend([settled, settled])

    summary = drain(
        1,
        deadline_seconds=5,
        already_terminal=frozenset(),
    )

    assert summary.reached_limit
    assert summary.terminal_count == 1


def test_retried_work_that_was_terminal_at_baseline_counts_toward_the_limit(
    ledger: list[list[FakeItem]],
) -> None:
    """An operator retry must count even when the key was FAILED at startup."""
    failed = [item("retry-me", StageExecutionState.FAILED)]
    ledger.extend(
        [
            failed,
            [item("retry-me", StageExecutionState.ADMITTED)],
            [item("retry-me", StageExecutionState.SUCCEEDED)],
        ]
    )

    summary = drain(
        1,
        deadline_seconds=5,
        already_terminal=frozenset({"retry-me"}),
    )

    assert summary.reached_limit
    assert summary.terminal_count == 1


def test_pre_existing_terminal_without_retry_does_not_count(
    ledger: list[list[FakeItem]],
) -> None:
    failed = [item("stuck", StageExecutionState.FAILED)]
    ledger.extend([failed, failed, failed])

    summary = drain(
        1,
        deadline_seconds=0.3,
        already_terminal=frozenset({"stuck"}),
    )

    assert not summary.reached_limit
    assert summary.deadline_expired
    assert summary.terminal_count == 0


def test_the_watchdog_reports_failure_to_make_progress(
    ledger: list[list[FakeItem]],
) -> None:
    """Reaching the deadline is never a success condition."""
    ledger.append([item("a", StageExecutionState.ADMITTED)])

    summary = drain(1, deadline_seconds=0.3)

    assert not summary.reached_limit
    assert not summary.interrupted
    assert summary.deadline_expired
    assert summary.terminal_count == 0
