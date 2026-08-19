"""Utilities for parameter sweeps."""

import itertools
from pathlib import Path
from typing import Any, cast
import hydra
from hydra.core.global_hydra import GlobalHydra
from omegaconf import OmegaConf


def parse_sweep_params(params_str: str) -> dict[str, list[str]]:
    """Parse sweep parameters from string format.

    Example: "model=resnet18,resnet50 optim.lr=0.001,0.01"
    Returns: {"model": ["resnet18", "resnet50"], "optim.lr": ["0.001", "0.01"]}

    Args:
        params_str: String containing sweep parameters

    Returns:
        Dictionary mapping parameter names to lists of values
    """
    if not params_str:
        return {}

    result = {}
    # Split by whitespace to get individual param=values pairs
    pairs = params_str.split()
    for pair in pairs:
        if "=" not in pair:
            continue
        key, values = pair.split("=", 1)
        result[key] = [v.strip() for v in values.split(",")]
    return result


def generate_sweep_configs(
    base_config: str, sweep_params: dict[str, list[str]]
) -> list[dict[str, Any]]:
    """Generate all config combinations for a parameter sweep.

    Args:
        base_config: Path to base Hydra config file
        sweep_params: Parameters to sweep over

    Returns:
        List of composed configs
    """
    if not sweep_params:
        # No sweep, just load base config
        return [load_hydra_config(base_config, [])]

    # Generate all combinations
    keys = list(sweep_params.keys())
    values = [sweep_params[k] for k in keys]

    configs = []
    for combo in itertools.product(*values):
        overrides = [f"{k}={v}" for k, v in zip(keys, combo, strict=False)]
        config = load_hydra_config(base_config, overrides)
        configs.append(config)

    return configs


def load_hydra_config(config_path: str, overrides: list[str]) -> dict[str, Any]:
    """Load and compose a Hydra config with overrides.

    Args:
        config_path: Path to config file
        overrides: List of override strings (e.g., ["model=resnet50", "lr=0.01"])

    Returns:
        Composed config as dictionary
    """
    config_path_obj = Path(config_path).resolve()
    config_dir = config_path_obj.parent
    config_name = config_path_obj.name

    # Clear any existing Hydra state
    GlobalHydra.instance().clear()

    # Initialize and compose
    with hydra.initialize_config_dir(config_dir=str(config_dir), version_base=None):
        cfg = hydra.compose(config_name=config_name, overrides=overrides)
        # Convert to regular dict and resolve
        result = OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
        assert isinstance(result, dict), "Config must be a dictionary"
        return cast(dict[str, Any], result)


def validate_sweep_config(config: dict[str, Any]) -> None:
    """Validate that a config is ready for job submission.

    Args:
        config: Config dictionary to validate

    Raises:
        AssertionError: If config is invalid
    """
    # KNOWN ISSUE (see README): _target_ also validated in JobDB and CLI
    assert isinstance(config, dict), "Config must be a dictionary"
    assert "_target_" in config, "Config must include _target_ field"

    # Validate target is importable
    target = config["_target_"]
    try:
        module_path, func_name = target.rsplit(".", 1)
        import importlib

        module = importlib.import_module(module_path)
        assert hasattr(module, func_name), (
            f"Function {func_name} not found in {module_path}"
        )
    except Exception as e:
        raise AssertionError(f"Cannot import target {target}: {e}") from e
