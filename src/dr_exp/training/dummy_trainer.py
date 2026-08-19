"""A fast CPU trainer used by tests and smoke runs.

It implements the dr-exp trainer contract: one module-level synchronous
callable taking a strict-JSON request and returning a strict-JSON result,
writing artifacts under ``request["workspace"]`` and treating SIGTERM as
"checkpoint and exit".
"""

from __future__ import annotations

import json
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

DEFAULT_EPOCHS = 3
DEFAULT_GATE_TIMEOUT_SECONDS = 120.0

#: Written before the trainer blocks on a gate, so a test can synchronize on
#: the child actually running rather than on elapsed time.
STARTED_FILENAME = "started"
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
    (workspace / STARTED_FILENAME).write_text(str(request.get("attempt", 0)))

    if params.get(FAIL_PARAM):
        raise RuntimeError(f"dummy trainer asked to fail: {request.get('work_key')}")

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
        if _terminating or time.monotonic() >= deadline:
            return
        time.sleep(GATE_POLL_SECONDS)
    del workspace


__all__ = [
    "CHECKPOINT_FILENAME",
    "DEFAULT_EPOCHS",
    "EPOCHS_PARAM",
    "FAIL_PARAM",
    "GATE_PARAM",
    "GATE_TIMEOUT_PARAM",
    "STARTED_FILENAME",
    "train",
]
