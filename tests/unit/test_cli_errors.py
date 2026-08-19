"""Operator mistakes exit cleanly instead of printing a traceback.

dr-exp's failures arrive as three unrelated exception families, and none of
them means "dr-exp is broken": pydantic and dr-exp validation raise
``ValueError``, dr-platform's ledger conflicts are ``RuntimeError``s, and
inspection raises ``LookupError`` for a key that does not exist. The CLI group
turns all three into a ``ClickException``.
"""

from __future__ import annotations

from collections.abc import Iterator

import click
import pytest
from click.testing import CliRunner
from dr_platform import PipelineRunConflictError, RegistrationClosureError

from dr_exp.cli.main import cli

#: click's exit code for a ``ClickException``. A traceback would exit 1.
USAGE_ERROR_EXIT_CODE = 1


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def failing_command() -> Iterator[None]:
    """Register a throwaway command on the real group, then remove it."""
    yield
    cli.commands.pop("boom", None)


def register(error: BaseException) -> None:
    @cli.command(name="boom")
    def boom() -> None:
        raise error


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (PipelineRunConflictError("run 'demo' already exists"), "already exists"),
        (RegistrationClosureError("run 'demo' is closed"), "is closed"),
        (LookupError("no work item matches 'abc'"), "no work item matches"),
        (ValueError("labels must include 'accelerator'"), "must include"),
    ],
    ids=["run-conflict", "closed-run", "missing-key", "validation"],
)
def test_operator_errors_become_click_exceptions(
    runner: CliRunner,
    failing_command: None,
    error: Exception,
    expected: str,
) -> None:
    register(error)
    result = runner.invoke(cli, ["boom"])

    assert result.exit_code == USAGE_ERROR_EXIT_CODE
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert expected in result.output
    assert "Traceback" not in result.output


def test_a_genuine_bug_is_not_swallowed(
    runner: CliRunner, failing_command: None
) -> None:
    """Only the operator-error families are mapped.

    A ``TypeError`` means dr-exp called something wrongly, and hiding its
    traceback would make that unreportable.
    """
    register(TypeError("stage body got an unexpected keyword"))
    result = runner.invoke(cli, ["boom"])

    assert isinstance(result.exception, TypeError)


def test_click_exceptions_pass_through_unchanged(
    runner: CliRunner, failing_command: None
) -> None:
    register(click.ClickException("machine profile not found: /nope.yaml"))
    result = runner.invoke(cli, ["boom"])

    assert result.exit_code == USAGE_ERROR_EXIT_CODE
    assert "machine profile not found" in result.output
