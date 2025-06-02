import argparse
from typing import Optional

from dr_exp.worker import default_train, run_worker


def build_arg_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the worker script."""

    parser = argparse.ArgumentParser(description="Run a single worker process")
    parser.add_argument("--base-path", default=".", help="Base path for mock DB")
    parser.add_argument("--work-dir", required=True, help="Local working directory")
    parser.add_argument("--max-claim-attempts", type=int, default=5)
    parser.add_argument("--heartbeat-interval", type=float, default=5.0)
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    """Command line entry point for a worker."""

    args = build_arg_parser().parse_args(argv)
    run_worker(
        base_path=args.base_path,
        work_dir=args.work_dir,
        max_claim_attempts=args.max_claim_attempts,
        heartbeat_interval=args.heartbeat_interval,
    )


if __name__ == "__main__":
    main()

__all__ = ["run_worker", "default_train", "build_arg_parser", "main"]
