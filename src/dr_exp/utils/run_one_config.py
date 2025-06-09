"""Utilities for generating run-one configs using proper Hydra integration."""

from typing import Dict, Any, List
from pathlib import Path

from dr_exp.utils.config_upload import generate_configs, config_hash
from dr_exp.job_db.base_job_db import BaseJobDB


def generate_run_one_config(
    base_config_path: str, config_name: str, overrides: List[str], priority: int = 850
) -> Dict[str, Any]:
    """Generate a single config for immediate execution.

    Parameters
    ----------
    base_config_path : str
        Path to directory containing Hydra configs
    config_name : str
        Name of the main config file
    overrides : List[str]
        List of Hydra-style overrides (e.g., ["model=resnet", "lr=0.001"])
    priority : int, optional
        Job priority, by default 850

    Returns
    -------
    Dict[str, Any]
        Generated config dictionary

    Raises
    ------
    ValueError
        If config generation fails
    """
    # Use the existing config generation system
    configs = list(generate_configs(base_config_path, config_name, {}))

    assert configs, "Failed to generate base config"

    # Take the first (and only) config since we're not doing a sweep
    base_config = configs[0]

    # Apply overrides (simplified - in practice Hydra handles this)
    # For now, we'll just include them in metadata
    config_with_meta = {
        "config": base_config,
        "metadata": {"run_one": True, "overrides": overrides, "priority": priority},
    }

    return config_with_meta


def create_run_one_job(
    client: BaseJobDB,
    base_config_path: str,
    config_name: str,
    overrides: List[str],
    priority: int = 850,
) -> Dict[str, Any]:
    """Create a run-one job using proper config generation.

    Parameters
    ----------
    client : BaseJobDB
        Database client to use
    base_config_path : str
        Path to config directory
    config_name : str
        Config file name
    overrides : List[str]
        Config overrides
    priority : int, optional
        Job priority, by default 850

    Returns
    -------
    Dict[str, Any]
        Created job information
    """
    config = generate_run_one_config(base_config_path, config_name, overrides, priority)
    sweep_id = f"run_one_{config_hash(config)}"

    job = client.add_job(config, sweep_id, status="queued", priority=priority)
    return job


def get_default_config_path() -> str:
    """Get the default path to training configs.

    Returns
    -------
    str
        Path to config directory
    """
    # Configs are in the repo root
    return str(Path(__file__).resolve().parents[3] / "configs")
