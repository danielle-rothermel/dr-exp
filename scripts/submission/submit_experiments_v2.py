#!/usr/bin/env python3
"""Improved experiment submission script with safety features."""

import argparse
import subprocess
import sys
import time
from pathlib import Path

from submission_utils import JobSubmitter


def main():
    parser = argparse.ArgumentParser(
        description="Submit chronological ablation experiments"
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
        default=[0, 1, 2],
        help="Random seeds to use (default: 0 1 2)",
    )
    parser.add_argument(
        "--only-failed",
        action="store_true",
        help="Only submit previously failed jobs from log",
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

    args = parser.parse_args()

    # Define all experiments
    experiments = [
        ("step00_baseline.yaml", 170),
        ("step01_sgd.yaml", 160),
        ("step02_no_randaug.yaml", 150),
        ("step03_no_cutmix.yaml", 140),
        ("step04_no_mixup.yaml", 130),
        ("step05_no_warmup.yaml", 120),
        ("step06_steplr.yaml", 110),
        ("step07_no_residual.yaml", 100),
        ("step08_lrn_dropout.yaml", 90),
        ("step09_xavier.yaml", 80),
        ("step10_no_lrn.yaml", 70),
        ("step11_resnet12.yaml", 60),
        ("step12_alexnet.yaml", 50),
        ("step13_no_dropout.yaml", 40),
        ("step14_tanh.yaml", 30),
        ("step15_no_colorjitter.yaml", 20),
        ("step16_no_rrc.yaml", 10),
        ("step17_no_hflip.yaml", 0),
    ]

    # Initialize submitter
    submitter = JobSubmitter(args.base_path, args.experiment, args.dry_run)

    # Pre-validation
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

    # Check existing jobs
    existing_jobs = set()
    if args.skip_existing and not args.force:
        print("\n🔍 Checking for existing jobs...")
        existing_jobs = submitter.check_existing_jobs()
        if existing_jobs:
            print(f"Found {len(existing_jobs)} existing jobs that will be skipped.")

    # Calculate total jobs
    total_new_jobs = 0
    jobs_to_submit = []

    for config, priority in experiments:
        config_name = config.replace(".yaml", "")
        for seed in args.seeds:
            if args.force or (config_name, seed) not in existing_jobs:
                jobs_to_submit.append((config_name, seed, priority))
                total_new_jobs += 1

    if total_new_jobs == 0:
        print("\n✅ All jobs already exist! Nothing to submit.")
        return 0

    # Show summary
    print("\n📊 Submission Summary:")
    print(f"  Total configs: {len(experiments)}")
    print(f"  Seeds per config: {len(args.seeds)}")
    print(f"  Total possible jobs: {len(experiments) * len(args.seeds)}")
    print(
        f"  Existing jobs to skip: {len(experiments) * len(args.seeds) - total_new_jobs}"
    )
    print(f"  New jobs to submit: {total_new_jobs}")

    if args.dry_run:
        print("\n🚀 DRY RUN MODE - No jobs will actually be submitted")
    # Confirmation prompt for large submissions
    elif total_new_jobs > 20:
        response = input(
            f"\n⚠️  About to submit {total_new_jobs} jobs. Continue? [y/N]: "
        )
        if response.lower() != "y":
            print("Aborted.")
            return 0

    # Submit jobs
    print(f"\n🚀 Submitting {total_new_jobs} jobs...")

    successful = 0
    for i, (config_name, seed, priority) in enumerate(jobs_to_submit, 1):
        print(
            f"[{i}/{total_new_jobs}] Submitting {config_name}, seed={seed}, priority={priority}...",
            end=" ",
        )

        success, job_id = submitter.submit_job(f"{config_name}.yaml", seed, priority)

        if success:
            print(f"✓ {job_id}")
            successful += 1
        else:
            print("✗")

        # Small delay to avoid overwhelming the system
        if not args.dry_run and i < total_new_jobs:
            time.sleep(0.1)

    # Print summary
    print(f"\n📈 Results: {successful}/{total_new_jobs} jobs submitted successfully")

    if not args.dry_run:
        # Run status check
        print("\n📊 Current job status:")
        subprocess.run(
            [
                "dr_exp",
                "--base-path",
                str(args.base_path),
                "--experiment",
                args.experiment,
                "status",
            ],
            check=False,
        )

    # Print failure summary if any
    submitter.print_summary()

    return 0 if successful == total_new_jobs else 1


if __name__ == "__main__":
    sys.exit(main())
