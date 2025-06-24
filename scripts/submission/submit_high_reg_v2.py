#!/usr/bin/env python3
"""Improved high regularization experiment submission with safety features."""

import argparse
import subprocess
import sys
import time
from pathlib import Path

from submission_utils import JobSubmitter


def setup_argument_parser() -> argparse.ArgumentParser:
    """Setup and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Submit high regularization experiments"
    )
    parser.add_argument(
        "--base-path", type=Path, default=Path.cwd(), help="Base path for experiments"
    )
    parser.add_argument("--experiment", default="test", help="Experiment name")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be submitted without actually submitting",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[0, 1, 2, 3, 4],
        help="Random seeds to use (default: 0 1 2 3 4)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip jobs that already exist (default: True)",
    )
    parser.add_argument(
        "--force", action="store_true", help="Submit all jobs even if they exist"
    )
    return parser


def validate_configs(
    submitter: JobSubmitter, experiments: list[tuple[str, int]]
) -> int:
    """Validate that all configuration files exist."""
    print("🔍 Validating configuration files...")
    missing_configs = []
    for config, _ in experiments:
        if not submitter.validate_config(f"exp_configs/{config}"):
            missing_configs.append(config)

    if missing_configs:
        print("\n❌ Missing config files:")
        for config in missing_configs:
            print(f"  - {config}")
        print("\nPlease ensure all config files exist before submission.")
        return 1

    print("✅ All config files found!")
    return 0


def prepare_jobs(
    args: argparse.Namespace,
    experiments: list[tuple[str, int]],
    existing_jobs: set[tuple[str, int]],
) -> tuple[list[tuple[str, int, int]], int]:
    """Prepare the list of jobs to submit."""
    jobs_to_submit = []
    total_new_jobs = 0

    for config, priority in experiments:
        config_name = config.replace(".yaml", "")
        for seed in args.seeds:
            if args.force or (config_name, seed) not in existing_jobs:
                jobs_to_submit.append((config_name, seed, priority))
                total_new_jobs += 1

    return jobs_to_submit, total_new_jobs


def print_submission_summary(
    experiments: list[tuple[str, int]],
    args: argparse.Namespace,
    total_new_jobs: int,
    existing_count: int,
) -> None:
    """Print the submission summary."""
    print("\n📊 High Regularization Experiment Summary:")
    print(
        f"  Configurations: "
        f"{', '.join(c.replace('.yaml', '') for c, _ in experiments)}"
    )
    print(f"  Seeds per config: {len(args.seeds)} ({args.seeds})")
    print(f"  Total possible jobs: {len(experiments) * len(args.seeds)}")
    print(f"  Existing jobs to skip: {existing_count}")
    print(f"  New jobs to submit: {total_new_jobs}")


def submit_jobs_batch(
    submitter: JobSubmitter,
    jobs_to_submit: list[tuple[str, int, int]],
    args: argparse.Namespace,
) -> int:
    """Submit jobs in batch with progress tracking."""
    total_jobs = len(jobs_to_submit)
    print(f"\n🚀 Submitting {total_jobs} jobs...")

    successful = 0
    for i, (config_name, seed, priority) in enumerate(jobs_to_submit, 1):
        print(
            f"[{i}/{total_jobs}] {config_name} seed={seed} priority={priority}",
            end=" ",
        )

        success, job_id = submitter.submit_job(f"{config_name}.yaml", seed, priority)

        if success:
            print(f"✓ {job_id if job_id else ''}")
            successful += 1
        else:
            print("✗")

        # Small delay to avoid overwhelming the system
        if not args.dry_run and i < total_jobs:
            time.sleep(0.2)  # Slightly longer delay for stability

    return successful


def run_status_check(args: argparse.Namespace, successful: int) -> None:
    """Run status check if not in dry run mode and jobs were submitted."""
    if not args.dry_run and successful > 0:
        print("\n📊 Current job status:")
        subprocess.run(  # noqa: S603
            [  # noqa: S607
                "dr_exp",
                "--base-path",
                str(args.base_path),
                "--experiment",
                args.experiment,
                "status",
            ],
            check=False,
        )


def main() -> int:
    args = setup_argument_parser().parse_args()

    # Define high regularization experiments
    high_reg_configs = [
        ("step00_baseline_high_reg.yaml", 100),
        ("step01_sgd_high_reg.yaml", 90),
        ("step02_no_randaug_high_reg.yaml", 80),
        ("step03_no_cutmix_high_reg.yaml", 70),
        ("step04_no_mixup_high_reg.yaml", 60),
    ]

    # Initialize submitter
    submitter = JobSubmitter(args.base_path, args.experiment, args.dry_run)

    # Validate configuration files
    validation_result = validate_configs(submitter, high_reg_configs)
    if validation_result != 0:
        return validation_result

    # Check existing jobs
    existing_jobs = set()
    if args.skip_existing and not args.force:
        print("\n🔍 Checking for existing jobs...")
        existing_jobs = submitter.check_existing_jobs()
        if existing_jobs:
            print(f"Found {len(existing_jobs)} existing jobs that will be skipped.")

    # Prepare jobs to submit
    jobs_to_submit, total_new_jobs = prepare_jobs(args, high_reg_configs, existing_jobs)

    if total_new_jobs == 0:
        print("\n✅ All jobs already exist! Nothing to submit.")
        return 0

    # Show summary
    existing_count = len(high_reg_configs) * len(args.seeds) - total_new_jobs
    print_submission_summary(high_reg_configs, args, total_new_jobs, existing_count)

    if args.dry_run:
        print("\n🚀 DRY RUN MODE - No jobs will actually be submitted")
    else:
        # Confirmation prompt
        response = input(
            f"\n⚠️  About to submit {total_new_jobs} jobs. Continue? [y/N]: "
        )
        if response.lower() != "y":
            print("Aborted.")
            return 0

    # Submit jobs
    successful = submit_jobs_batch(submitter, jobs_to_submit, args)

    # Print results
    print(f"\n📈 Results: {successful}/{total_new_jobs} jobs submitted successfully")

    # Run status check
    run_status_check(args, successful)

    # Print failure summary if any
    submitter.print_summary()

    return 0 if successful == total_new_jobs else 1


if __name__ == "__main__":
    sys.exit(main())
