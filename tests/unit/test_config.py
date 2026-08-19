"""Job configuration parsing, validation, and sweep expansion."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from dr_exp.config.job import (
    DEFAULT_PRIORITY,
    MAX_PRIORITY,
    ConfigError,
    JobConfig,
    SweepSpec,
    load_job_config,
    load_sweep_spec,
    validate_entry_point_importable,
)
from dr_exp.config.names import Accelerator

VALID_ENTRY_POINT = "dr_exp.training.dummy_trainer:train"


def make_config(**overrides: object) -> JobConfig:
    fields: dict[str, object] = {
        "entry_point": VALID_ENTRY_POINT,
        "labels": {"accelerator": "cpu"},
    }
    fields.update(overrides)
    return JobConfig.model_validate(fields)


def test_defaults_are_the_documented_baseline() -> None:
    config = make_config()
    assert config.priority == DEFAULT_PRIORITY == 100
    assert config.params == {}
    assert config.tags == ()
    assert config.budgets is None


def test_entry_point_parts_split_on_the_colon() -> None:
    assert make_config().entry_point_parts == (
        "dr_exp.training.dummy_trainer",
        "train",
    )


def test_accelerator_property_reads_the_label() -> None:
    assert make_config(labels={"accelerator": "mps"}).accelerator is (Accelerator.MPS)


@pytest.mark.parametrize(
    "entry_point",
    [
        "dr_exp.training.dummy_trainer.train",
        "dr_exp.training.dummy_trainer:",
        ":train",
        "dr_exp.training.dummy trainer:train",
        "dr_exp.training.dummy_trainer:not an identifier",
        "1bad.module:train",
    ],
)
def test_malformed_entry_points_are_rejected(entry_point: str) -> None:
    with pytest.raises(ValidationError):
        make_config(entry_point=entry_point)


def test_labels_must_declare_an_accelerator() -> None:
    with pytest.raises(ValidationError, match="accelerator"):
        make_config(labels={})


def test_accelerator_label_must_be_known() -> None:
    with pytest.raises(ValidationError, match="accelerator"):
        make_config(labels={"accelerator": "tpu"})


def test_priority_is_bounded_by_the_platform_range() -> None:
    assert make_config(priority=0).priority == 0
    assert make_config(priority=MAX_PRIORITY).priority == MAX_PRIORITY
    with pytest.raises(ValidationError):
        make_config(priority=-1)
    with pytest.raises(ValidationError):
        make_config(priority=MAX_PRIORITY + 1)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        make_config(unexpected="value")


def test_budget_wall_time_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        make_config(budgets={"wall_time_seconds": 0})


def test_entry_point_importability_accepts_the_dummy_trainer() -> None:
    validate_entry_point_importable(
        make_config(), python_executable=Path(sys.executable)
    )


def test_entry_point_importability_rejects_a_missing_module() -> None:
    with pytest.raises(ConfigError, match="not importable"):
        validate_entry_point_importable(
            make_config(entry_point="dr_exp.no_such_module:train"),
            python_executable=Path(sys.executable),
        )


def test_entry_point_importability_rejects_a_missing_attribute() -> None:
    with pytest.raises(ConfigError, match="no attribute"):
        validate_entry_point_importable(
            make_config(entry_point="dr_exp.training.dummy_trainer:absent"),
            python_executable=Path(sys.executable),
        )


def test_entry_point_importability_rejects_a_non_callable() -> None:
    with pytest.raises(ConfigError, match="not callable"):
        validate_entry_point_importable(
            make_config(entry_point="dr_exp.training.dummy_trainer:DEFAULT_EPOCHS"),
            python_executable=Path(sys.executable),
        )


def test_entry_point_importability_uses_isolated_subprocess_with_dash_i(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        args: list[str], *, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    validate_entry_point_importable(
        make_config(), python_executable=Path(sys.executable)
    )
    assert calls[0][:3] == [str(Path(sys.executable)), "-I", "-c"]


def test_entry_point_importability_uses_the_profile_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        args: list[str], *, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    other = Path("/opt/train-venv/bin/python")
    validate_entry_point_importable(make_config(), python_executable=other)
    assert calls[0][0] == str(other)
    assert calls[0][1] == "-I"


def test_sweep_without_a_grid_is_a_single_point() -> None:
    spec = SweepSpec(base=make_config())
    assert spec.expand() == (spec.base,)


def test_sweep_expands_the_cartesian_product_in_order() -> None:
    spec = SweepSpec(
        base=make_config(params={"epochs": 2}),
        grid={"lr": [0.1, 0.01], "seed": [1, 2]},
    )
    expanded = spec.expand()
    assert [config.params for config in expanded] == [
        {"epochs": 2, "lr": 0.1, "seed": 1},
        {"epochs": 2, "lr": 0.1, "seed": 2},
        {"epochs": 2, "lr": 0.01, "seed": 1},
        {"epochs": 2, "lr": 0.01, "seed": 2},
    ]


def test_sweep_grid_overrides_base_params() -> None:
    spec = SweepSpec(base=make_config(params={"epochs": 2}), grid={"epochs": [5]})
    assert spec.expand()[0].params == {"epochs": 5}


def test_sweep_preserves_non_param_fields() -> None:
    spec = SweepSpec(base=make_config(priority=7, tags=("a",)), grid={"lr": [0.1, 0.2]})
    assert all(config.priority == 7 for config in spec.expand())
    assert all(config.tags == ("a",) for config in spec.expand())


def test_sweep_rejects_an_empty_axis() -> None:
    with pytest.raises(ValidationError, match="at least one value"):
        SweepSpec(base=make_config(), grid={"lr": []})


def test_sweep_rejects_a_dotted_axis_name() -> None:
    """A Hydra-style dotted path would silently become a flat literal key.

    ``optim.lr`` used to address nested config. Here it would produce a param
    named ``"optim.lr"`` that no trainer reads, so it is rejected outright.
    """
    with pytest.raises(ValidationError, match="not dotted paths"):
        SweepSpec(base=make_config(), grid={"optim.lr": [0.1]})


def test_load_job_config_reads_the_bundled_example() -> None:
    config = load_job_config(Path("configs/examples/dummy_train.yaml"))
    assert config.entry_point == VALID_ENTRY_POINT
    assert config.accelerator is Accelerator.CPU


def test_load_sweep_spec_reads_the_bundled_example() -> None:
    spec = load_sweep_spec(Path("configs/examples/dummy_sweep.yaml"))
    assert len(spec.expand()) == 2


def test_load_job_config_rejects_a_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- one\n- two\n")
    with pytest.raises(ConfigError, match="mapping"):
        load_job_config(path)


def test_load_job_config_rejects_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("a: [1,\n")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_job_config(path)
