import argparse
import os
import shutil


def reset_mock_db(base_path: str = ".") -> None:
    """Remove all mock database and storage files then recreate empty dirs."""
    mock_db_path = os.path.join(base_path, "mock_db")
    mock_storage_path = os.path.join(base_path, "mock_storage")
    jobs_dir = os.path.join(mock_db_path, "jobs")
    metrics_dir = os.path.join(mock_db_path, "metrics")
    errors_file = os.path.join(mock_db_path, "errors.jsonl")

    # Remove directories and files if they exist
    for path in (jobs_dir, metrics_dir, mock_storage_path):
        if os.path.exists(path):
            shutil.rmtree(path)

    if os.path.exists(errors_file):
        os.remove(errors_file)

    # Recreate clean structure
    os.makedirs(jobs_dir, exist_ok=True)
    os.makedirs(metrics_dir, exist_ok=True)
    os.makedirs(mock_storage_path, exist_ok=True)
    with open(errors_file, "w"):
        pass


def main() -> None:
    """CLI wrapper for :func:`reset_mock_db`."""

    parser = argparse.ArgumentParser(description="Reset the mock Supabase environment.")
    parser.add_argument(
        "--base-path",
        default=".",
        help="Base path containing mock_db and mock_storage directories",
    )
    args = parser.parse_args()
    reset_mock_db(args.base_path)
    print(f"Mock database reset under {os.path.abspath(args.base_path)}")


if __name__ == "__main__":
    main()
