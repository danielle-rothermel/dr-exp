"""Job and sweep configuration parsed from YAML.

``JobConfig`` is the boundary type: one training attempt's entry point,
parameters, routing labels, priority, and budgets. ``SweepSpec`` expands a base
config across a Cartesian grid.
"""

from __future__ import annotations

import itertools
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dr_exp.config.names import Accelerator, LabelKey

#: Baseline submission priority. dr-platform treats *lower* as sooner and 0 as
#: the highest priority, so dr-exp submits in the middle of the range and
#: ``dr_exp boost`` lowers the number.
DEFAULT_PRIORITY = 100

#: dr-platform's inclusive upper bound on work priority.
MAX_PRIORITY = 2_147_483_647

type JsonValue = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


class ConfigError(ValueError):
    """A configuration document is not a valid dr-exp declaration."""


class Budgets(BaseModel):
    """Resource limits enforced by dr-exec on the training child process."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    wall_time_seconds: Annotated[float, Field(gt=0)] | None = None


class JobConfig(BaseModel):
    """One training attempt's complete declaration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_point: str
    params: dict[str, JsonValue] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    priority: Annotated[int, Field(ge=0, le=MAX_PRIORITY)] = DEFAULT_PRIORITY
    budgets: Budgets | None = None
    tags: tuple[str, ...] = ()

    @field_validator("entry_point")
    @classmethod
    def _entry_point_is_well_formed(cls, value: str) -> str:
        module_name, separator, attribute_name = value.partition(":")
        if not separator or not module_name or not attribute_name:
            raise ValueError(
                f"entry_point must be 'package.module:function', got {value!r}"
            )
        if not all(part.isidentifier() for part in module_name.split(".")):
            raise ValueError(
                f"entry_point module must be a dotted Python module, got "
                f"{module_name!r}"
            )
        if not attribute_name.isidentifier():
            raise ValueError(
                f"entry_point attribute must be an identifier, got {attribute_name!r}"
            )
        return value

    @model_validator(mode="after")
    def _labels_declare_a_known_accelerator(self) -> Self:
        accelerator = self.labels.get(LabelKey.ACCELERATOR)
        if accelerator is None:
            raise ValueError(
                f"labels must include {LabelKey.ACCELERATOR.value!r}; "
                f"one of {sorted(a.value for a in Accelerator)}"
            )
        if accelerator not in {a.value for a in Accelerator}:
            raise ValueError(
                f"labels[{LabelKey.ACCELERATOR.value!r}] must be one of "
                f"{sorted(a.value for a in Accelerator)}, got {accelerator!r}"
            )
        return self

    @property
    def accelerator(self) -> Accelerator:
        """The accelerator this job routes to."""
        return Accelerator(self.labels[LabelKey.ACCELERATOR])

    @property
    def entry_point_parts(self) -> tuple[str, str]:
        """The ``(module_name, attribute_name)`` pair of ``entry_point``."""
        module_name, _, attribute_name = self.entry_point.partition(":")
        return module_name, attribute_name


class SweepSpec(BaseModel):
    """A base job plus a Cartesian grid over parameter values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base: JobConfig
    grid: dict[str, list[JsonValue]] = Field(default_factory=dict)

    @field_validator("grid")
    @classmethod
    def _grid_axes_are_non_empty(
        cls, value: dict[str, list[JsonValue]]
    ) -> dict[str, list[JsonValue]]:
        empty = sorted(name for name, values in value.items() if not values)
        if empty:
            raise ValueError(f"sweep grid axes must list at least one value: {empty}")
        return value

    @field_validator("grid")
    @classmethod
    def _grid_axes_are_flat_param_names(
        cls, value: dict[str, list[JsonValue]]
    ) -> dict[str, list[JsonValue]]:
        """Reject dotted axis names instead of creating a flat param for them.

        Hydra read ``a.b`` as a path into nested config. This model does not:
        an axis name is one ``params`` key, so ``a.b`` would silently produce a
        literal ``"a.b"`` param that the trainer never reads.
        """
        dotted = sorted(name for name in value if "." in name)
        if dotted:
            raise ValueError(
                f"sweep grid axes must be flat 'params' keys, not dotted paths: "
                f"{dotted}"
            )
        return value

    def expand(self) -> tuple[JobConfig, ...]:
        """Return one ``JobConfig`` per point of the Cartesian grid.

        Grid axes override ``base.params`` by key. With no grid, the base
        config is the single point.
        """
        if not self.grid:
            return (self.base,)
        axis_names = list(self.grid)
        value_lists = [self.grid[name] for name in axis_names]
        return tuple(
            self.base.model_copy(
                update={
                    "params": {
                        **self.base.params,
                        **dict(zip(axis_names, point, strict=True)),
                    }
                }
            )
            for point in itertools.product(*value_lists)
        )


def validate_entry_point_importable(
    config: JobConfig, *, python_executable: Path
) -> None:
    """Reject a job whose entry point cannot be imported in the training venv.

    Submission is the one place this is checked; the worker trusts the ledger.
    Validation runs under ``python_executable``, not the CLI process, so a
    controller can submit against a profile whose interpreter differs.
    """
    module_name, attribute_name = config.entry_point_parts
    if python_executable == Path(sys.executable):
        _validate_entry_point_in_process(module_name, attribute_name, config)
        return

    script = f"""
import importlib
import sys

module_name = {module_name!r}
attribute_name = {attribute_name!r}
try:
    module = importlib.import_module(module_name)
except ImportError as error:
    print(f"entry_point module is not importable: {{module_name!r}}: {{error}}")
    sys.exit(1)
try:
    attribute = getattr(module, attribute_name)
except AttributeError:
    print(
        f"entry_point module {{module_name!r}} has no attribute {{attribute_name!r}}"
    )
    sys.exit(2)
if not callable(attribute):
    print(f"entry_point {module_name}:{attribute_name!r} is not callable")
    sys.exit(3)
"""
    result = subprocess.run(  # noqa: S603 -- interpreter comes from a validated profile
        [str(python_executable), "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return
    message = (
        result.stderr.strip() or result.stdout.strip() or "entry_point check failed"
    )
    raise ConfigError(message)


def _validate_entry_point_in_process(
    module_name: str, attribute_name: str, config: JobConfig
) -> None:
    import importlib

    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise ConfigError(
            f"entry_point module is not importable: {module_name!r}: {error}"
        ) from error
    try:
        attribute = getattr(module, attribute_name)
    except AttributeError as error:
        raise ConfigError(
            f"entry_point module {module_name!r} has no attribute {attribute_name!r}"
        ) from error
    if not callable(attribute):
        raise ConfigError(f"entry_point {config.entry_point!r} is not callable")


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise ConfigError(f"{path} is not valid YAML: {error}") from error
    if not isinstance(document, dict):
        raise ConfigError(f"{path} must contain a YAML mapping")
    return document


def load_job_config(path: Path) -> JobConfig:
    """Parse one ``JobConfig`` from a YAML file."""
    return JobConfig.model_validate(_load_yaml_mapping(path))


def load_sweep_spec(path: Path) -> SweepSpec:
    """Parse one ``SweepSpec`` from a YAML file."""
    return SweepSpec.model_validate(_load_yaml_mapping(path))


__all__ = [
    "DEFAULT_PRIORITY",
    "MAX_PRIORITY",
    "Budgets",
    "ConfigError",
    "JobConfig",
    "JsonValue",
    "SweepSpec",
    "load_job_config",
    "load_sweep_spec",
    "validate_entry_point_importable",
]
