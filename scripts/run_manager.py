"""Command line entry point for the manager."""

import argparse
import os
from typing import List

from dr_exp.manager import Manager, discover_gpus


def build_arg_parser() -> argparse.ArgumentParser:
    """Return the command line argument parser."""
    parser = argparse.ArgumentParser(description="SLURM Manager")
    parser.add_argument("--gpus-per-node", type=int, default=1)
    parser.add_argument("--workers-per-gpu", type=int, default=1)
    parser.add_argument("--heartbeat-interval", type=int, default=10)
    parser.add_argument("--idle-timeout-mins", type=int, default=30)
    return parser


def main(argv: List[str] | None = None) -> None:
    """Entry point for the manager command line tool."""
    args = build_arg_parser().parse_args(argv)
    gpus = discover_gpus(args.gpus_per_node)
    slurm_job_id = os.environ.get("SLURM_JOB_ID", str(os.getpid()))
    base_dir = os.path.join("./manager_runs", f"job_{slurm_job_id}")
    manager = Manager(
        gpus=gpus,
        workers_per_gpu=args.workers_per_gpu,
        heartbeat_interval=args.heartbeat_interval,
        idle_timeout_mins=args.idle_timeout_mins,
        base_dir=base_dir,
    )
    manager.run()


if __name__ == "__main__":  # pragma: no cover - script entry
    main()
