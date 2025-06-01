"""Hydra based Config Generator and uploader using :class:`SupabaseMockClient`."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from typing import Any, Dict, Iterable, List, Sequence

import hydra
from hydra.core.global_hydra import GlobalHydra
from omegaconf import OmegaConf

from dr_exp.mock.supabase_mock_client import SupabaseMockClient


def parse_sweep(sweep: str) -> Dict[str, List[str]]:
    """Parse a sweep definition string into a mapping.

    The sweep string uses Hydra's multirun CLI style where each item is of the
    form ``param=val1,val2`` separated by spaces.
    """
    sweep = sweep.strip()
    if not sweep:
        return {}

    params: Dict[str, List[str]] = {}
    for item in sweep.split():
        if "=" not in item:
            continue
        key, values = item.split("=", 1)
        params[key] = values.split(",")
    return params


def _generate_override_combinations(
    sweep_params: Dict[str, List[str]],
) -> Iterable[List[str]]:
    """Yield lists of override strings for all parameter combinations."""
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
    """Compose Hydra configs for all combinations of sweep parameters."""
    GlobalHydra.instance().clear()
    with hydra.initialize_config_dir(config_dir=base_config_path, version_base=None):
        for overrides in _generate_override_combinations(sweep_params):
            cfg = hydra.compose(config_name=config_name, overrides=overrides)
            yield OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)


def config_hash(cfg: Dict[str, Any]) -> str:
    """Compute SHA256 hash of a configuration dictionary."""
    cfg_json = json.dumps(cfg, sort_keys=True)
    return hashlib.sha256(cfg_json.encode("utf-8")).hexdigest()


def upload_configs(
    base_config_path: str,
    config_name: str,
    sweep: str,
    client: SupabaseMockClient,
    cluster_name: str | None = None,
    description: str | None = None,
    interface_version: str | None = None,
    code_version: str | None = None,
) -> List[Dict[str, Any]]:
    """Generate configs using Hydra and upload them using the mock client."""

    sweep_params = parse_sweep(sweep)

    created_jobs = []
    for cfg in generate_configs(base_config_path, config_name, sweep_params):
        sweep_id = config_hash(cfg)
        metadata = {
            "cluster_name": cluster_name,
            "description": description,
            "interface_version": interface_version,
            "code_version": code_version,
        }
        cfg_with_meta = {"config": cfg, "metadata": metadata}
        job = client.add_job(cfg_with_meta, sweep_id, status="queued")
        created_jobs.append(job)
    return created_jobs


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and upload configs.")
    parser.add_argument(
        "--base-config-path",
        required=True,
        help="Directory containing Hydra config files",
    )
    parser.add_argument(
        "--config-name",
        required=True,
        help="Name of the main config file (e.g. config.yaml)",
    )
    parser.add_argument("--sweep", default="", help="Sweep definition")
    parser.add_argument("--cluster-name")
    parser.add_argument("--description")
    parser.add_argument("--interface-version")
    parser.add_argument("--code-version")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    client = SupabaseMockClient()
    jobs = upload_configs(
        base_config_path=args.base_config_path,
        config_name=args.config_name,
        sweep=args.sweep,
        client=client,
        cluster_name=args.cluster_name,
        description=args.description,
        interface_version=args.interface_version,
        code_version=args.code_version,
    )
    print(f"Created {len(jobs)} job(s)")


if __name__ == "__main__":
    main()
