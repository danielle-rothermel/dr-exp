import argparse
from typing import Optional

from dr_exp.utils.jobdb_factory import get_supabase_client
from dr_exp.utils.storage_cleanup import cleanup_uploaded_runs


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remove run directories that have been uploaded"
    )
    parser.add_argument(
        "--base-path",
        default=".",
        help="Base path for SupabaseMockClient",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    args = build_arg_parser().parse_args(argv)
    client = get_supabase_client(base_path=args.base_path)
    count = cleanup_uploaded_runs(client)
    print(f"Removed {count} run directory(s)")


if __name__ == "__main__":
    main()

__all__ = ["cleanup_uploaded_runs", "build_arg_parser", "main"]
