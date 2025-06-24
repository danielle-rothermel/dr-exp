#!/usr/bin/env python3
"""Unified job submission script with all safety features."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from submission_utils import JobSubmitter

# Constants for display limits and thresholds
MAX_DISPLAYED_FAILED_JOBS = 5
MAX_DISPLAYED_JOB_PREVIEW = 3
LARGE_SUBMISSION_THRESHOLD = 10


# Experiment definitions
CHRONOLOGICAL_EXPERIMENTS = [
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

HIGH_REG_EXPERIMENTS = [
    ("step00_baseline_high_reg.yaml", 100),
    ("step01_sgd_high_reg.yaml", 90),
    ("step02_no_randaug_high_reg.yaml", 80),
    ("step03_no_cutmix_high_reg.yaml", 70),
    ("step04_no_mixup_high_reg.yaml", 60),
]


def load_failed_jobs(log_dir: Path) -> list[tuple[str, int]]:
    """Load failed jobs from the most recent log file."""
    if not log_dir.exists():
        return []

    # Find most recent log file
    log_files = sorted(log_dir.glob("submission_*.json"), reverse=True)
    if not log_files:
        return []

    failed_jobs = []
    with log_files[0].open() as f:
        data = json.load(f)
        failed_jobs.extend(
            (submission["config"].replace(".yaml", ""), submission["seed"])
            for submission in data.get("submissions", [])
            if not submission["success"]
        )

    return failed_jobs


def setup_argument_parser() -> argparse.ArgumentParser:
    """Setup and configure the comprehensive argument parser."""
    parser = argparse.ArgumentParser(
        description="Unified job submission with safety features",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Submit all chronological experiments with dry run
  %(prog)s --experiment-type chrono --dry-run

  # Submit high-reg experiments, skipping existing
  %(prog)s --experiment-type high-reg --skip-existing

  # Submit specific configs with default seeds
  %(prog)s --configs step00_baseline step01_sgd

  # Submit specific configs with custom seeds
  %(prog)s --configs step00_baseline step01_sgd --seeds 0 1 2

  # Submit with custom priority
  %(prog)s --configs step00_baseline --priority 200

  # Retry failed jobs from last run
  %(prog)s --retry-failed

  # Submit with custom seeds
  %(prog)s --experiment-type chrono --seeds 10 11 12
""",
    )

    parser.add_argument(
        "--base-path", type=Path, default=Path.cwd(), help="Base path for experiments"
    )
    parser.add_argument("--experiment", default="test", help="Experiment name")
    parser.add_argument(
        "--experiment-type",
        choices=["chrono", "high-reg", "both"],
        help="Which experiment set to run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be submitted without actually submitting",
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
    parser.add_argument(
        "--configs",
        nargs="+",
        help="Specific config names to submit (e.g., step00_baseline step01_sgd)",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        help=(
            "Seeds to use with --configs (default: 0,1,2 for chrono; 0-4 for high-reg)"
        ),
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=None,
        help="Priority for submitted jobs (default: use predefined priorities)",
    )
    parser.add_argument(
        "--overrides",
        type=str,
        default=None,
        help="Additional Hydra overrides (e.g., 'machine=mac,epochs=2')",
    )
    parser.add_argument(
        "--tags",
        type=str,
        default=None,
        help="Comma-separated tags to apply to all jobs (e.g., 'baseline,gpu-test')",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry failed jobs from the most recent submission",
    )
    parser.add_argument(
        "--no-confirm", action="store_true", help="Skip confirmation prompts"
    )
    return parser


def determine_jobs_from_retry_failed(
    args: argparse.Namespace,
) -> list[tuple[str, int, int]]:
    """Determine jobs to submit from failed job retry."""
    log_dir = args.base_path / args.experiment / "submission_logs"
    failed = load_failed_jobs(log_dir)
    if not failed:
        print("No failed jobs found in recent logs.")
        return []

    print(f"Found {len(failed)} failed jobs to retry:")
    for config, seed in failed[:MAX_DISPLAYED_FAILED_JOBS]:  # Show first few
        print(f"  - {config}, seed={seed}")
    if len(failed) > MAX_DISPLAYED_FAILED_JOBS:
        print(f"  ... and {len(failed) - MAX_DISPLAYED_FAILED_JOBS} more")

    # Look up priorities
    all_experiments = CHRONOLOGICAL_EXPERIMENTS + HIGH_REG_EXPERIMENTS
    priority_map = {cfg.replace(".yaml", ""): pri for cfg, pri in all_experiments}

    jobs_to_submit = []
    for config, seed in failed:
        priority = priority_map.get(config, 0)
        jobs_to_submit.append((config, seed, priority))

    return jobs_to_submit


def determine_jobs_from_configs(args: argparse.Namespace) -> list[tuple[str, int, int]]:
    """Determine jobs to submit from specific config list."""
    all_experiments = CHRONOLOGICAL_EXPERIMENTS + HIGH_REG_EXPERIMENTS
    priority_map = {cfg.replace(".yaml", ""): pri for cfg, pri in all_experiments}

    # Determine seeds to use
    if args.seeds:
        seeds = args.seeds
    else:
        # Default seeds based on config type
        # Check if any config is high-reg
        has_high_reg = any("high_reg" in cfg for cfg in args.configs)
        seeds = [0, 1, 2, 3, 4] if has_high_reg else [0, 1, 2]

    jobs_to_submit = []
    for config in args.configs:
        # Clean up config name (remove .yaml if present)
        config_clean = config.replace(".yaml", "")

        # Use custom priority if provided, otherwise look up default
        if args.priority is not None:
            priority = args.priority
        else:
            priority = priority_map.get(config_clean, 0)
            if priority == 0 and config_clean not in priority_map:
                print(f"Warning: Unknown config '{config_clean}', using priority 0")

        jobs_to_submit.extend((config_clean, seed, priority) for seed in seeds)

    return jobs_to_submit


def determine_jobs_from_experiment_type(
    args: argparse.Namespace,
) -> list[tuple[str, int, int]]:
    """Determine jobs to submit from experiment type selection."""
    experiments = []

    if args.experiment_type in {"chrono", "both"}:
        seeds = args.seeds if args.seeds else [0, 1, 2]
        experiments.extend(
            (cfg.replace(".yaml", ""), seed, pri)
            for cfg, pri in CHRONOLOGICAL_EXPERIMENTS
            for seed in seeds
        )

    if args.experiment_type in {"high-reg", "both"}:
        seeds = args.seeds if args.seeds else [0, 1, 2, 3, 4]
        experiments.extend(
            (cfg.replace(".yaml", ""), seed, pri)
            for cfg, pri in HIGH_REG_EXPERIMENTS
            for seed in seeds
        )

    return experiments


def determine_jobs_to_submit(args: argparse.Namespace) -> list[tuple[str, int, int]]:
    """Determine which jobs to submit based on arguments."""
    if args.retry_failed:
        return determine_jobs_from_retry_failed(args)
    elif args.configs:
        return determine_jobs_from_configs(args)
    elif args.experiment_type:
        return determine_jobs_from_experiment_type(args)
    else:
        print("Please specify --experiment-type or --configs")
        return []


def validate_configs(
    submitter: JobSubmitter, jobs_to_submit: list[tuple[str, int, int]]
) -> int:
    """Validate that all required configuration files exist."""
    print("🔍 Validating configuration files...")
    configs_to_check = list({job[0] + ".yaml" for job in jobs_to_submit})
    missing_configs = [
        config
        for config in configs_to_check
        if not submitter.validate_config(f"exp_configs/{config}")
    ]

    if missing_configs:
        print("\n❌ Missing config files:")
        for config in missing_configs:
            print(f"  - {config}")
        print("\nPlease ensure all config files exist before submission.")
        return 1

    print(f"✅ All {len(configs_to_check)} config files validated!")
    return 0


def filter_existing_jobs(
    jobs_to_submit: list[tuple[str, int, int]],
    existing_jobs: set[tuple[str, int]],
    args: argparse.Namespace,
) -> tuple[list[tuple[str, int, int]], int]:
    """Filter out existing jobs from the submission list."""
    filtered_jobs = []
    skipped = 0
    for config, seed, priority in jobs_to_submit:
        if args.force or (config, seed) not in existing_jobs:
            filtered_jobs.append((config, seed, priority))
        else:
            skipped += 1

    return filtered_jobs, skipped


def print_submission_summary(
    jobs_to_submit: list[tuple[str, int, int]],
    filtered_jobs: list[tuple[str, int, int]],
    skipped: int,
) -> None:
    """Print comprehensive submission summary."""
    print("\n📊 Submission Summary:")
    print(f"  Total jobs requested: {len(jobs_to_submit)}")
    if skipped > 0:
        print(f"  Existing jobs to skip: {skipped}")
    print(f"  New jobs to submit: {len(filtered_jobs)}")

    # Show first few jobs as preview
    print("\n  First few jobs:")
    for config, seed, priority in filtered_jobs[:MAX_DISPLAYED_JOB_PREVIEW]:
        print(f"    - {config}, seed={seed}, priority={priority}")
    if len(filtered_jobs) > MAX_DISPLAYED_JOB_PREVIEW:
        print(f"    ... and {len(filtered_jobs) - MAX_DISPLAYED_JOB_PREVIEW} more")


def handle_dry_run(filtered_jobs: list[tuple[str, int, int]]) -> None:
    """Handle dry run mode by showing what would be submitted."""
    print("\n🚀 DRY RUN MODE - No jobs will actually be submitted")
    print("\nWould submit the following jobs:")
    for i, (config, seed, priority) in enumerate(filtered_jobs, 1):
        print(f"  [{i}] {config}, seed={seed}, priority={priority}")


def get_user_confirmation(
    filtered_jobs: list[tuple[str, int, int]], args: argparse.Namespace
) -> bool:
    """Get user confirmation for large submissions."""
    if args.no_confirm or len(filtered_jobs) <= LARGE_SUBMISSION_THRESHOLD:
        return True

    response = input(
        f"\n⚠️  About to submit {len(filtered_jobs)} jobs. Continue? [y/N]: "
    )
    return response.lower() == "y"


def submit_jobs_batch(
    submitter: JobSubmitter,
    filtered_jobs: list[tuple[str, int, int]],
    args: argparse.Namespace,
) -> int:
    """Submit jobs in batch with progress tracking."""
    print(f"\n🚀 Submitting {len(filtered_jobs)} jobs...")

    successful = 0
    for i, (config, seed, priority) in enumerate(filtered_jobs, 1):
        print(f"[{i}/{len(filtered_jobs)}] {config} seed={seed}", end=" ")

        # Parse tags if provided
        tag_list = []
        if args.tags:
            tag_list = [t.strip() for t in args.tags.split(",") if t.strip()]

        success, job_id = submitter.submit_job(
            f"{config}.yaml",
            seed,
            priority,
            extra_overrides=args.overrides,
            tags=tag_list,
        )

        if success:
            print(f"✓ {job_id if job_id else ''}")
            successful += 1
        else:
            print("✗")

        # Small delay to avoid overwhelming the system
        if i < len(filtered_jobs):
            time.sleep(0.1)

    return successful


def run_status_check(args: argparse.Namespace, successful: int) -> None:
    """Run status check if jobs were successfully submitted."""
    if successful > 0:
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

    # Initialize submitter
    submitter = JobSubmitter(args.base_path, args.experiment, args.dry_run)

    # Determine which jobs to submit
    jobs_to_submit = determine_jobs_to_submit(args)
    if not jobs_to_submit:
        return 0 if args.retry_failed else 1

    # Validate configuration files
    validation_result = validate_configs(submitter, jobs_to_submit)
    if validation_result != 0:
        return validation_result

    # Check existing jobs
    existing_jobs = set()
    if args.skip_existing and not args.force:
        print("\n🔍 Checking for existing jobs...")
        existing_jobs = submitter.check_existing_jobs()
        if existing_jobs:
            print(f"Found {len(existing_jobs)} existing jobs.")

    # Filter out existing jobs
    filtered_jobs, skipped = filter_existing_jobs(jobs_to_submit, existing_jobs, args)

    if not filtered_jobs:
        print("\n✅ All jobs already exist! Nothing to submit.")
        return 0

    # Show summary
    print_submission_summary(jobs_to_submit, filtered_jobs, skipped)

    if args.dry_run:
        handle_dry_run(filtered_jobs)
        return 0

    # Get confirmation
    if not get_user_confirmation(filtered_jobs, args):
        print("Aborted.")
        return 0

    # Submit jobs
    successful = submit_jobs_batch(submitter, filtered_jobs, args)

    # Print results
    print(
        f"\n📈 Results: {successful}/{len(filtered_jobs)} jobs submitted successfully"
    )

    # Run status check
    run_status_check(args, successful)

    # Print failure summary if any
    submitter.print_summary()

    return 0 if successful == len(filtered_jobs) else 1


if __name__ == "__main__":
    sys.exit(main())
