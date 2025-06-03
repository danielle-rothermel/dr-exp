import argparse
from typing import Optional

from dr_exp.core.client_provider import get_supabase_client
from dr_exp.utils.job_reaper import reap_stale_jobs


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mark stale running jobs as failed")
    parser.add_argument(
        "--max-age-mins",
        type=int,
        default=60,
        help="Heartbeat age threshold in minutes",
    )
    parser.add_argument("--base-path", default=".", help="Base path for LocalDBClient")
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    args = build_arg_parser().parse_args(argv)
    client = get_supabase_client(base_path=args.base_path)
    count = reap_stale_jobs(client, args.max_age_mins)
    print(f"Marked {count} stale job(s) as failed")


if __name__ == "__main__":
    main()

__all__ = ["reap_stale_jobs", "build_arg_parser", "main"]
