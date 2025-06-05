import argparse
import os
import shutil


def reset_job_db(base_path: str = ".") -> None:
    """Remove all mock database and storage files then recreate empty dirs."""
    jobs_dir = os.path.join(base_path, "jobs")
    metrics_dir = os.path.join(base_path, "metrics")
    errors_file = os.path.join(base_path, "errors.jsonl")

    # Remove directories and files if they exist
    for path in (jobs_dir, metrics_dir):
        if os.path.exists(path):
            shutil.rmtree(path)

    if os.path.exists(errors_file):
        os.remove(errors_file)

    # Recreate clean structure
    os.makedirs(jobs_dir, exist_ok=True)
    os.makedirs(metrics_dir, exist_ok=True)
    with open(errors_file, "w"):
        pass


def main() -> None:
    """CLI wrapper for :func:`reset_job_db`."""

    parser = argparse.ArgumentParser(description="Reset the local jobdb environment.")
    parser.add_argument(
        "--base-path",
        default=".",
        help="Base path containing job data",
    )
    args = parser.parse_args()
    reset_job_db(args.base_path)
    print(f"JobDB reset under {os.path.abspath(args.base_path)}")


if __name__ == "__main__":
    main()
