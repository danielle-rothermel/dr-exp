"""Hydra based Config Generator and uploader."""

from __future__ import annotations

from pathlib import Path
import argparse
import os
from typing import Any, Dict, List, Sequence

from dr_exp.utils import config_upload
from dr_exp.utils.jobdb_factory import get_supabase_client
from dr_exp.job_db.local_job_db import LocalJobDB


def add_arguments(parser: argparse.ArgumentParser) -> None:
    self_dir_absolute = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--base-config-path",
        default=str(self_dir_absolute / "configs"),
        help="Directory containing Hydra config files",
    )
    parser.add_argument(
        "--config-name",
        default="config.yaml",
        help="Name of the main config file (e.g. config.yaml)",
    )
    parser.add_argument("--sweep", default="", help="Sweep definition")
    parser.add_argument("--cluster-name")
    parser.add_argument("--description")
    parser.add_argument("--interface-version")
    parser.add_argument("--code-version")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and upload configs.")
    add_arguments(parser)
    return parser


def run(args: argparse.Namespace) -> List[Dict[str, Any]]:
    if os.environ.get("EXPMGR_MODE", "mock").lower() == "real":
        client = get_supabase_client()
    else:
        client = LocalJobDB()
    return config_upload.upload_configs(
        base_config_path=args.base_config_path,
        config_name=args.config_name,
        sweep=args.sweep,
        client=client,
        cluster_name=args.cluster_name,
        description=args.description,
        interface_version=args.interface_version,
        code_version=args.code_version,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    jobs = run(args)
    print(f"Created {len(jobs)} job(s)")


if __name__ == "__main__":
    main()
