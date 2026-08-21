"""The CLI owns logging configuration, so library log records reach stderr.

dr-exp's library modules never configure logging. Without the group callback
doing it, dr-platform's INFO reconciliation lines -- the dispatcher's sweep
summary among them -- are dropped before an operator can see them.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from dr_exp.cli.main import (
    DEFAULT_LOG_LEVEL,
    LOG_LEVELS,
    _configure_logging,
    cli,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@contextmanager
def bare_root_logger() -> Iterator[logging.Logger]:
    """Present an unconfigured root logger, then restore what was there.

    Observing what the CLI configures requires a bare root. pytest's logging
    plugin attaches its capture handlers for the call phase, i.e. *after*
    fixture setup, so this has to be entered from inside the test body rather
    than supplied as a fixture. Handlers are restored intact, leaving log
    capture working normally for every other test.
    """
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    root.handlers = []
    root.setLevel(logging.WARNING)
    try:
        yield root
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)


@pytest.fixture
def probe() -> Iterator[str]:
    """A dr-platform-shaped logger name, reset so it inherits from root."""
    name = "dr_platform.runtime.dispatcher"
    logger = logging.getLogger(name)
    saved_level = logger.level
    saved_propagate = logger.propagate
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
    try:
        yield name
    finally:
        logger.setLevel(saved_level)
        logger.propagate = saved_propagate


@pytest.fixture
def echo_command() -> Iterator[str]:
    """A throwaway command that emits one library-style INFO record."""
    name = "log-probe"

    @cli.command(name=name)
    def log_probe() -> None:
        logging.getLogger("dr_platform.runtime.dispatcher").info(
            "abandoned-stage sweep inspected=0 projected=0; identity_unavailable=False"
        )
        logging.getLogger("dr_platform.runtime.dispatcher").debug("quiet detail")

    yield name
    cli.commands.pop(name, None)


def test_the_group_installs_a_stderr_handler_at_the_default_level(
    runner: CliRunner, echo_command: str, probe: str
) -> None:
    with bare_root_logger() as root:
        result = runner.invoke(cli, [echo_command])

        assert result.exit_code == 0
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], logging.StreamHandler)


def test_a_library_info_record_propagates_to_the_configured_handler(
    runner: CliRunner, echo_command: str, probe: str
) -> None:
    """The record dr-platform actually emits must survive to output."""
    with bare_root_logger():
        result = runner.invoke(cli, [echo_command])

    assert result.exit_code == 0
    assert "identity_unavailable=False" in result.output
    assert probe in result.output
    assert "quiet detail" not in result.output


def test_log_level_debug_admits_debug_records(
    runner: CliRunner, echo_command: str, probe: str
) -> None:
    with bare_root_logger() as root:
        result = runner.invoke(cli, ["--log-level", "DEBUG", echo_command])
        level = root.level

    assert result.exit_code == 0
    assert level == logging.DEBUG
    assert "quiet detail" in result.output


def test_log_level_is_case_insensitive(
    runner: CliRunner, echo_command: str, probe: str
) -> None:
    with bare_root_logger() as root:
        result = runner.invoke(cli, ["--log-level", "warning", echo_command])
        level = root.level

    assert result.exit_code == 0
    assert level == logging.WARNING
    assert "identity_unavailable" not in result.output


def test_an_unknown_log_level_is_rejected(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--log-level", "LOUD", "list", "--machine", "mini"])

    assert result.exit_code != 0
    assert "LOUD" in result.output


def test_the_level_choices_and_default_are_the_documented_ones() -> None:
    assert LOG_LEVELS == ("DEBUG", "INFO", "WARNING", "ERROR")
    assert DEFAULT_LOG_LEVEL in LOG_LEVELS
    assert all(getattr(logging, level) for level in LOG_LEVELS)


def test_configuring_twice_does_not_stack_handlers(
    runner: CliRunner, echo_command: str, probe: str
) -> None:
    """A second invoke reuses the installed handler and rebinds its stream.

    Duplicated handlers would double every line an operator reads. The stream
    is rebound so the second invocation's records reach its own stderr, not
    the first invocation's capture. The level is also re-applied, which is
    what makes ``--log-level`` still take effect.
    """
    with bare_root_logger() as root:
        first = runner.invoke(cli, [echo_command])
        installed = root.handlers[:]
        assert len(installed) == 1
        assert "identity_unavailable=False" in first.output

        second = runner.invoke(cli, ["--log-level", "DEBUG", echo_command])

        assert root.handlers == installed
        assert root.level == logging.DEBUG
        assert "identity_unavailable=False" in second.output
        assert "quiet detail" in second.output
        assert second.output.count("identity_unavailable=False") == 1


def test_a_second_configure_rebinds_the_owned_handler_to_current_stderr(
    probe: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_stream = io.StringIO()
    second_stream = io.StringIO()
    logger = logging.getLogger(probe)

    with bare_root_logger() as root:
        monkeypatch.setattr("sys.stderr", first_stream)
        _configure_logging("INFO")
        logger.info("first invocation")

        monkeypatch.setattr("sys.stderr", second_stream)
        _configure_logging("INFO")
        logger.info("second invocation")

        assert len(root.handlers) == 1
        assert "first invocation" in first_stream.getvalue()
        assert "second invocation" in second_stream.getvalue()
        assert "second invocation" not in first_stream.getvalue()


def test_an_existing_logging_setup_is_left_alone() -> None:
    """An embedding process keeps its own handlers; only the level moves."""
    with bare_root_logger() as root:
        existing = logging.NullHandler()
        root.addHandler(existing)

        _configure_logging("WARNING")

        assert root.handlers == [existing]
        assert root.level == logging.WARNING
