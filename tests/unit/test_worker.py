"""Worker startup helpers such as stage capacity bootstrapping."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from dr_exp.config.machine import MachineProfile
from dr_exp.config.names import Accelerator, LabelKey
from dr_exp.platform.worker import ensure_stage_capacity


def make_profile(
    tmp_path: Path, *, accelerator: Accelerator = Accelerator.MPS
) -> MachineProfile:
    return MachineProfile.model_validate(
        {
            "name": "unit",
            "accelerator": accelerator.value,
            "python_executable": Path("/opt/venv/bin/python"),
            "workspace_root": tmp_path / "workspace",
            "run_store_root": tmp_path / "runs",
            "database_url": "postgresql+psycopg:///dr_exp_test",
            "system_database_url": "postgresql+psycopg:///dr_exp_test",
            "executor_id": "unit-0",
            "worker_concurrency": 2,
        }
    )


@dataclass(frozen=True)
class FakeControl:
    """Minimal stand-in for dr-platform capacity control records."""

    selector: dict[str, str]
    capacity: int = 1


def test_ensure_stage_capacity_seeds_default_and_mps_selector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_set_stage_capacity(**kwargs: Any) -> None:  # noqa: ANN401
        calls.append(("stage", kwargs))

    def fake_set_selector_capacity(**kwargs: Any) -> None:  # noqa: ANN401
        calls.append(("selector", kwargs))

    monkeypatch.setattr("dr_platform.read_controls", lambda **_kwargs: [])
    monkeypatch.setattr("dr_platform.set_stage_capacity", fake_set_stage_capacity)
    monkeypatch.setattr(
        "dr_platform.set_selector_capacity",
        fake_set_selector_capacity,
    )

    ensure_stage_capacity(
        make_profile(tmp_path, accelerator=Accelerator.MPS), engine=MagicMock()
    )

    assert len(calls) == 2
    assert calls[0][0] == "stage"
    assert calls[0][1]["capacity"] == 2
    assert calls[1][0] == "selector"
    assert calls[1][1]["labels"] == {LabelKey.ACCELERATOR.value: Accelerator.MPS.value}
    assert calls[1][1]["capacity"] == 2


def test_ensure_stage_capacity_skips_controls_that_already_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = [
        FakeControl(selector={}),
        FakeControl(selector={LabelKey.ACCELERATOR.value: Accelerator.MPS.value}),
    ]
    stage_calls: list[object] = []
    selector_calls: list[object] = []

    monkeypatch.setattr("dr_platform.read_controls", lambda **_kwargs: existing)
    monkeypatch.setattr(
        "dr_platform.set_stage_capacity",
        lambda **_kwargs: stage_calls.append(True),
    )
    monkeypatch.setattr(
        "dr_platform.set_selector_capacity",
        lambda **_kwargs: selector_calls.append(True),
    )

    ensure_stage_capacity(
        make_profile(tmp_path, accelerator=Accelerator.MPS), engine=MagicMock()
    )

    assert stage_calls == []
    assert selector_calls == []
