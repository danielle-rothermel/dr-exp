"""Utilities for generating and uploading experiment configs."""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from typing import Any, Dict, Iterable, List

import hydra
from hydra.core.global_hydra import GlobalHydra
from omegaconf import OmegaConf

from dr_exp.job_db.base_job_db import BaseJobDB


# --------------------- Config Generation ---------------------


def parse_sweep(sweep: str) -> Dict[str, List[str]]:
    """Parse a Hydra-style sweep string."""
    sweep = sweep.strip()
    if not sweep:
        return {}

    params: Dict[str, List[str]] = {}
    pattern = r"([\w.]+)\s*=\s*([^=]+?)(?=\s+[\w.]+\s*=|$)"
    for match in re.finditer(pattern, sweep):
        key, values = match.groups()
        params[key.strip()] = [v.strip() for v in values.split(",") if v.strip()]
    return params


def _generate_override_combinations(
    sweep_params: Dict[str, List[str]],
) -> Iterable[List[str]]:
    if not sweep_params:
        yield []
        return

    keys = list(sweep_params)
    values_product = itertools.product(*(sweep_params[k] for k in keys))
    for combo in values_product:
        yield [f"{k}={v}" for k, v in zip(keys, combo)]


def generate_configs(
    base_config_path: str, config_name: str, sweep_params: Dict[str, List[str]]
) -> Iterable[Dict[str, Any]]:
    GlobalHydra.instance().clear()
    with hydra.initialize_config_dir(config_dir=base_config_path, version_base=None):
        for overrides in _generate_override_combinations(sweep_params):
            cfg = hydra.compose(config_name=config_name, overrides=overrides)
            container = OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
            assert isinstance(container, dict), f"Expected dict, got {type(container)}"
            yield container  # type: ignore[misc]


def config_hash(cfg: Dict[str, Any]) -> str:
    cfg_json = json.dumps(cfg, sort_keys=True)
    return hashlib.sha256(cfg_json.encode("utf-8")).hexdigest()


# --------------------- Upload Logic ---------------------


def upload_configs(
    base_config_path: str,
    config_name: str,
    sweep: str,
    client: BaseJobDB,
    cluster_name: str | None = None,
    description: str | None = None,
    interface_version: str | None = None,
    code_version: str | None = None,
    priority: int = 100,
) -> List[Dict[str, Any]]:
    sweep_params = parse_sweep(sweep)

    created_jobs: List[Dict[str, Any]] = []
    for cfg in generate_configs(base_config_path, config_name, sweep_params):
        sweep_id = config_hash(cfg)
        metadata = {
            "cluster_name": cluster_name,
            "description": description,
            "interface_version": interface_version,
            "code_version": code_version,
        }
        cfg_with_meta = {"config": cfg, "metadata": metadata}
        job = client.add_job(
            cfg_with_meta, sweep_id, status="queued", priority=priority
        )
        created_jobs.append(job)
    return created_jobs


__all__ = [
    "parse_sweep",
    "generate_configs",
    "config_hash",
    "upload_configs",
]
