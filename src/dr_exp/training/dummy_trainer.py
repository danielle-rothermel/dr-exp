"""A fast CPU trainer used by tests and smoke runs.

It implements the dr-exp trainer contract: one module-level synchronous
callable taking a strict-JSON request and returning a strict-JSON result,
writing artifacts under ``request["workspace"]`` and treating SIGTERM as
"checkpoint and exit".
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from types import FrameType
from typing import Any

#: Parameter names this trainer understands, all optional.
EPOCHS_PARAM = "epochs"
GATE_PARAM = "gate_file"
GATE_TIMEOUT_PARAM = "gate_timeout_seconds"
FAIL_PARAM = "fail"
RETURN_NON_JSON_PARAM = "return_non_json"
FAIL_UNTIL_PARAM = "fail_until_file"
SHUTDOWN_DELAY_PARAM = "shutdown_delay_seconds"

DEFAULT_EPOCHS = 3
DEFAULT_GATE_TIMEOUT_SECONDS = 120.0

#: Written before the trainer blocks on a gate, so a test can synchronize on
#: the child actually running rather than on elapsed time.
STARTED_FILENAME = "started"

#: The training child's own PID, written beside ``STARTED_FILENAME``. A test
#: that cancels an attempt reads this to prove the child process is really
#: gone, which no workspace artifact can show: a child hung on its gate leaves
#: exactly the same files behind as one that was torn down.
PID_FILENAME = "child.pid"
CHECKPOINT_FILENAME = "checkpoint.json"
GATE_POLL_SECONDS = 0.02

_terminating = False


def _request_shutdown(_signum: int, _frame: FrameType | None) -> None:
    global _terminating  # noqa: PLW0603 -- one process-wide shutdown flag
    _terminating = True


def train(request: dict[str, Any]) -> dict[str, Any]:
    """Run a dummy training attempt.

    Args:
        request: The dr-exp trainer request: ``params``, ``workspace``,
            ``work_key``, and ``attempt``.

    Returns:
        A strict-JSON result describing the completed epochs and metrics.
    """
    global _terminating  # noqa: PLW0603 -- reset per in-process invocation
    _terminating = False
    signal.signal(signal.SIGTERM, _request_shutdown)

    params: dict[str, Any] = request.get("params") or {}
    workspace = Path(request["workspace"])
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / PID_FILENAME).write_text(str(os.getpid()))
    (workspace / STARTED_FILENAME).write_text(str(request.get("attempt", 0)))

    if params.get(FAIL_PARAM):
        raise RuntimeError(f"dummy trainer asked to fail: {request.get('work_key')}")

    fail_until = params.get(FAIL_UNTIL_PARAM)
    if fail_until and not Path(fail_until).exists():
        # Fails until the named file appears, which lets a test drive one
        # attempt to failure and the retry of it to success without depending
        # on attempt numbering or on how many times a body is recovered.
        raise RuntimeError(
            f"dummy trainer failing until {fail_until} exists: "
            f"{request.get('work_key')}"
        )

    if params.get(RETURN_NON_JSON_PARAM):
        # A trainer that violates the strict-JSON half of the contract. dr-exec
        # rejects this at the result boundary rather than letting a
        # half-serializable object reach the ledger.
        return {"workspace": workspace}

    _wait_for_gate(params, workspace=workspace)

    epochs = int(params.get(EPOCHS_PARAM, DEFAULT_EPOCHS))
    metrics: list[dict[str, float]] = []
    completed = 0
    for epoch in range(epochs):
        if _terminating:
            break
        metrics.append(
            {
                "epoch": float(epoch),
                "loss": round(1.0 / (epoch + 1), 6),
                "accuracy": round(min(0.99, (epoch + 1) / epochs), 6),
            }
        )
        completed = epoch + 1
        _checkpoint(workspace, metrics)

    return {
        "work_key": request.get("work_key"),
        "attempt": request.get("attempt"),
        "epochs_completed": completed,
        "interrupted": _terminating,
        "metrics": metrics[-1] if metrics else None,
    }


def _checkpoint(workspace: Path, metrics: list[dict[str, float]]) -> None:
    (workspace / CHECKPOINT_FILENAME).write_text(
        json.dumps({"metrics": metrics}, indent=2)
    )


def _wait_for_gate(params: dict[str, Any], *, workspace: Path) -> None:
    """Block until a gate file appears, SIGTERM arrives, or the budget ends.

    A gate lets a test hold an attempt in flight deterministically instead of
    guessing at a sleep long enough to cancel within.
    """
    gate = params.get(GATE_PARAM)
    if not gate:
        return
    gate_path = Path(gate)
    timeout = float(params.get(GATE_TIMEOUT_PARAM, DEFAULT_GATE_TIMEOUT_SECONDS))
    deadline = time.monotonic() + timeout
    while not gate_path.exists():
        if _terminating:
            _shut_down(params)
            return
        if time.monotonic() >= deadline:
            return
        time.sleep(GATE_POLL_SECONDS)
    del workspace


def _shut_down(params: dict[str, Any]) -> None:
    """Model a trainer that needs time to checkpoint before exiting.

    A real trainer does not vanish the instant SIGTERM lands; it finishes
    writing state first. Without that delay a cancelled child exits so fast
    that a caller which never waits for teardown looks identical to one that
    does.
    """
    delay = float(params.get(SHUTDOWN_DELAY_PARAM, 0.0))
    if delay > 0:
        time.sleep(delay)


__all__ = [
    "CHECKPOINT_FILENAME",
    "DEFAULT_EPOCHS",
    "EPOCHS_PARAM",
    "FAIL_PARAM",
    "FAIL_UNTIL_PARAM",
    "GATE_PARAM",
    "GATE_TIMEOUT_PARAM",
    "PID_FILENAME",
    "RETURN_NON_JSON_PARAM",
    "SHUTDOWN_DELAY_PARAM",
    "STARTED_FILENAME",
    "train",
]
