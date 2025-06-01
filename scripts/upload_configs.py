"""Simple Config Generator and uploader using SupabaseMockClient."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Sequence

from dr_exp.mock.supabase_mock_client import SupabaseMockClient


def load_base_config(path: str) -> Dict[str, Any]:
    """Load base config from a JSON-formatted YAML file."""
    with open(path, "r") as f:
        return json.load(f)


def parse_value(value: str) -> Any:
    """Parse a string value into int, float, or str."""
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        return value


def parse_sweep(sweep: str) -> Dict[str, List[Any]]:
    """Parse a sweep definition string into a mapping."""
    sweep = sweep.strip()
    if not sweep:
        return {}

    params: Dict[str, List[Any]] = {}
    for item in sweep.split():
        if "=" not in item:
            continue
        key, values = item.split("=", 1)
        params[key] = [parse_value(v) for v in values.split(",")]
    return params


def set_nested(cfg: Dict[str, Any], key: str, value: Any) -> None:
    """Set a nested key (dot notation) in a dictionary."""
    parts = key.split(".")
    d = cfg
    for part in parts[:-1]:
        if part not in d or not isinstance(d[part], dict):
            d[part] = {}
        d = d[part]
    d[parts[-1]] = value


def generate_configs(
    base_cfg: Dict[str, Any], sweep_params: Dict[str, List[Any]]
) -> Iterable[Dict[str, Any]]:
    """Yield configs for all combinations of sweep parameters."""
    if not sweep_params:
        yield deepcopy(base_cfg)
        return

    keys = list(sweep_params)
    values_product = itertools.product(*(sweep_params[k] for k in keys))
    for combo in values_product:
        cfg = deepcopy(base_cfg)
        for key, value in zip(keys, combo):
            set_nested(cfg, key, value)
        yield cfg


def config_hash(cfg: Dict[str, Any]) -> str:
    """Compute SHA256 hash of JSON canonical representation."""
    cfg_json = json.dumps(cfg, sort_keys=True)
    return hashlib.sha256(cfg_json.encode("utf-8")).hexdigest()


def upload_configs(
    base_config: str,
    sweep: str,
    client: SupabaseMockClient,
    cluster_name: str | None = None,
    description: str | None = None,
    interface_version: str | None = None,
    code_version: str | None = None,
) -> List[Dict[str, Any]]:
    """Generate configs and upload them using the mock client."""
    base_cfg = load_base_config(base_config)
    sweep_params = parse_sweep(sweep)

    created_jobs = []
    for cfg in generate_configs(base_cfg, sweep_params):
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
    parser.add_argument("--base-config", required=True, help="Path to base YAML")
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
        base_config=args.base_config,
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
