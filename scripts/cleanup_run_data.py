import argparse
from typing import Optional

from dr_exp.utils.jobdb_factory import get_job_db_client
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


# TODO: add force arg to skip interactive approval
def main(argv: Optional[list[str]] = None) -> None:
    build_arg_parser().parse_args(argv)
    # TODO: Fix broken call, this now requires a job config
    client = get_job_db_client()
    # TODO: Verify this works
    all_storage = find_all_storage(client)
    # TODO: Get user approval for removal and then remove all
    assert False, "Unimplemented, fix todos!"




if __name__ == "__main__":
    main()

__all__ = ["cleanup_uploaded_runs", "build_arg_parser", "main"]
