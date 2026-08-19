"""Worker and dispatcher exit codes for bounded drains."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from dr_exp.cli.main import cli
from dr_exp.platform.drain import DrainSummary

USAGE_ERROR_EXIT_CODE = 1


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@contextmanager
def _patched_worker_runtime(
    monkeypatch: pytest.MonkeyPatch, summary: DrainSummary
) -> Iterator[None]:
    runtime = MagicMock()
    runtime.engine = object()
    runtime.cancellation = object()

    @contextmanager
    def fake_worker_runtime(*_args: object, **_kwargs: object) -> Iterator[Any]:
        yield runtime

    monkeypatch.setattr("dr_exp.cli.main.load_machine_profile", lambda _m: MagicMock())
    monkeypatch.setattr("dr_exp.platform.worker.worker_runtime", fake_worker_runtime)
    monkeypatch.setattr(
        "dr_exp.platform.drain.drain_until",
        lambda **_kwargs: summary,
    )
    yield


def test_worker_exits_nonzero_when_the_watchdog_expires(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = DrainSummary(
        terminal_count=0,
        reached_limit=False,
        interrupted=False,
        deadline_expired=True,
    )
    with _patched_worker_runtime(monkeypatch, summary):
        result = runner.invoke(
            cli,
            [
                "worker",
                "--machine",
                "mini",
                "--campaign",
                "default",
                "--deadline-seconds",
                "1",
            ],
        )

    assert result.exit_code == USAGE_ERROR_EXIT_CODE
    assert "Traceback" not in result.output


def test_worker_exits_nonzero_when_max_jobs_is_not_reached(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = DrainSummary(
        terminal_count=0,
        reached_limit=False,
        interrupted=False,
        deadline_expired=False,
    )
    with _patched_worker_runtime(monkeypatch, summary):
        result = runner.invoke(
            cli,
            [
                "worker",
                "--machine",
                "mini",
                "--campaign",
                "default",
                "--max-jobs",
                "2",
            ],
        )

    assert result.exit_code == USAGE_ERROR_EXIT_CODE


def test_dispatcher_exits_nonzero_when_the_watchdog_expires(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = DrainSummary(
        terminal_count=0,
        reached_limit=False,
        interrupted=False,
        deadline_expired=True,
    )
    with _patched_worker_runtime(monkeypatch, summary):
        result = runner.invoke(
            cli,
            ["dispatcher", "--machine", "mini", "--deadline-seconds", "1"],
        )

    assert result.exit_code == USAGE_ERROR_EXIT_CODE


def test_worker_exits_zero_after_a_successful_bounded_drain(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = DrainSummary(
        terminal_count=2,
        reached_limit=True,
        interrupted=False,
        deadline_expired=False,
    )
    with _patched_worker_runtime(monkeypatch, summary):
        result = runner.invoke(
            cli,
            [
                "worker",
                "--machine",
                "mini",
                "--campaign",
                "default",
                "--max-jobs",
                "2",
            ],
        )

    assert result.exit_code == 0
