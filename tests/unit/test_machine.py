"""Machine-profile parsing and the queue routing derived from it."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from dr_exp.config.job import ConfigError
from dr_exp.config.machine import (
    BUNDLED_PROFILE_DIR,
    DEFAULT_TERMINATION_GRACE_SECONDS,
    MachineProfile,
    load_machine_profile,
    profile_path,
)
from dr_exp.config.names import Accelerator, QueueName


def make_profile(tmp_path: Path, **overrides: Any) -> MachineProfile:  # noqa: ANN401
    fields: dict[str, Any] = {
        "name": "test",
        "accelerator": "cpu",
        "python_executable": sys.executable,
        "workspace_root": tmp_path / "workspace",
        "run_store_root": tmp_path / "runs",
        "database_url": "postgresql+psycopg:///dr_exp_test",
        "system_database_url": "postgresql+psycopg:///dr_exp_test",
        "executor_id": "test-0",
        "worker_concurrency": 2,
    }
    fields.update(overrides)
    return MachineProfile.model_validate(fields)


def test_defaults_match_the_documented_grace_period(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    assert profile.termination_grace_seconds == (DEFAULT_TERMINATION_GRACE_SECONDS)
    assert profile.device_env == {}
    assert profile.sweep_executor_ids == ()


def test_relative_paths_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="absolute"):
        make_profile(tmp_path, workspace_root=Path("relative/workspace"))


def test_user_paths_are_expanded(tmp_path: Path) -> None:
    profile = make_profile(tmp_path, workspace_root="~/dr-exp-workspace")
    assert profile.workspace_root == Path.home() / "dr-exp-workspace"


def test_roots_must_differ(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="different directories"):
        make_profile(
            tmp_path,
            workspace_root=tmp_path / "shared",
            run_store_root=tmp_path / "shared",
        )


def test_unknown_fields_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_profile(tmp_path, gpus_per_node=8)


def test_worker_concurrency_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_profile(tmp_path, worker_concurrency=0)


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"], ids=["empty", "spaces", "ws"])
def test_executor_id_must_not_be_blank(tmp_path: Path, blank: str) -> None:
    """A blank id fails as a profile error, not later inside DBOS config."""
    with pytest.raises(ValidationError, match="executor_id|at least 1 character"):
        make_profile(tmp_path, executor_id=blank)


@pytest.mark.parametrize(
    ("accelerator", "queue_name", "dequeued"),
    [
        (Accelerator.CPU, QueueName.TRAIN_CPU, (QueueName.TRAIN_CPU,)),
        (
            Accelerator.MPS,
            QueueName.TRAIN_MPS,
            (QueueName.TRAIN_CPU, QueueName.TRAIN_MPS),
        ),
        (
            Accelerator.CUDA,
            QueueName.TRAIN_CUDA,
            (QueueName.TRAIN_CPU, QueueName.TRAIN_CUDA),
        ),
    ],
)
def test_queue_routing_follows_the_accelerator(
    tmp_path: Path,
    accelerator: Accelerator,
    queue_name: QueueName,
    dequeued: tuple[QueueName, ...],
) -> None:
    profile = make_profile(tmp_path, accelerator=accelerator.value)
    assert profile.queue_name is queue_name
    assert profile.dequeued_queue_names == dequeued


def test_sweeping_executor_ids_default_to_this_executor(
    tmp_path: Path,
) -> None:
    assert make_profile(tmp_path).sweeping_executor_ids == frozenset({"test-0"})


def test_sweeping_executor_ids_use_the_static_set_when_declared(
    tmp_path: Path,
) -> None:
    profile = make_profile(tmp_path, sweep_executor_ids=["a", "b"])
    assert profile.sweeping_executor_ids == frozenset({"a", "b"})


def test_device_env_templates_render_the_device_slot(tmp_path: Path) -> None:
    profile = make_profile(tmp_path, device_env={"CUDA_VISIBLE_DEVICES": "{device}"})
    assert profile.resolve_device_env("3") == {"CUDA_VISIBLE_DEVICES": "3"}


def test_workspace_paths_are_per_work_key_and_attempt(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    assert profile.workspace_for("abc", 2) == (
        profile.workspace_root / "runs" / "abc" / "attempt-2"
    )
    assert profile.config_document_path("abc") == (
        profile.workspace_root / "configs" / "abc.json"
    )


def test_bundled_mini_profile_is_valid_for_this_machine() -> None:
    profile = load_machine_profile("mini")
    assert profile.name == "mini"
    assert profile.accelerator is Accelerator.MPS
    assert profile.database_url == profile.system_database_url


def test_bundled_mini_profile_carries_no_machine_specific_literal_home() -> None:
    """The shipped profile must survive a merge onto another checkout.

    Its interpreter and roots are written with ``~`` so they resolve against
    whoever runs it. Existence is deliberately not asserted: CI has no such
    path, and the profile is not exercised there.
    """
    document = yaml.safe_load((BUNDLED_PROFILE_DIR / "mini.yaml").read_text())
    for field in ("python_executable", "workspace_root", "run_store_root"):
        assert document[field].startswith("~/"), field

    profile = load_machine_profile("mini")
    assert profile.python_executable.is_absolute()
    assert profile.python_executable.is_relative_to(Path.home())
    assert profile.workspace_root.is_relative_to(Path.home())


def test_python_executable_expands_the_user_home(tmp_path: Path) -> None:
    profile = make_profile(tmp_path, python_executable="~/some-venv/bin/python")
    assert profile.python_executable == Path.home() / "some-venv/bin/python"


def test_database_urls_must_name_one_database(tmp_path: Path) -> None:
    """The ledger and the DBOS system tables must share a database.

    dr-platform does not check this, so the profile does.
    """
    with pytest.raises(ValidationError, match="same database"):
        make_profile(
            tmp_path,
            system_database_url="postgresql+psycopg:///dr_exp_other_test",
        )


def test_bundled_torch_profile_parses_as_declared_data() -> None:
    profile = load_machine_profile("torch")
    assert profile.accelerator is Accelerator.CUDA
    assert profile.device_env == {"CUDA_VISIBLE_DEVICES": "{device}"}
    assert profile.sweeping_executor_ids == frozenset({"torch-0"})


def test_bundled_profile_dir_lives_inside_the_package() -> None:
    assert BUNDLED_PROFILE_DIR.is_dir()
    assert BUNDLED_PROFILE_DIR.name == "machines"
    assert "dr_exp" in BUNDLED_PROFILE_DIR.parts
    assert (BUNDLED_PROFILE_DIR / "mini.yaml").is_file()
    assert (BUNDLED_PROFILE_DIR / "torch.yaml").is_file()


def test_profile_path_resolves_bare_names_against_the_bundle() -> None:
    assert profile_path("mini", directory=BUNDLED_PROFILE_DIR) == (
        BUNDLED_PROFILE_DIR / "mini.yaml"
    )
    assert profile_path("/opt/custom.yaml") == Path("/opt/custom.yaml")


def test_missing_profile_reports_the_path_it_looked_for() -> None:
    with pytest.raises(ConfigError, match="machine profile not found"):
        load_machine_profile("no-such-machine")
