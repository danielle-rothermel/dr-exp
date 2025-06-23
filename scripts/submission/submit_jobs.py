#!/usr/bin/env python3
"""Unified job submission script with all safety features."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from submission_utils import JobSubmitter


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
    with open(log_files[0]) as f:
        data = json.load(f)
        for submission in data.get("submissions", []):
            if not submission["success"]:
                failed_jobs.append(
                    (submission["config"].replace(".yaml", ""), submission["seed"])
                )

    return failed_jobs


def main():
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
        help="Seeds to use with --configs (default: 0,1,2 for chrono; 0-4 for high-reg)",
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

    args = parser.parse_args()

    # Initialize submitter
    submitter = JobSubmitter(args.base_path, args.experiment, args.dry_run)

    # Determine which jobs to submit
    jobs_to_submit = []

    if args.retry_failed:
        # Load failed jobs from most recent log
        log_dir = args.base_path / args.experiment / "submission_logs"
        failed = load_failed_jobs(log_dir)
        if not failed:
            print("No failed jobs found in recent logs.")
            return 0

        print(f"Found {len(failed)} failed jobs to retry:")
        for config, seed in failed[:5]:  # Show first 5
            print(f"  - {config}, seed={seed}")
        if len(failed) > 5:
            print(f"  ... and {len(failed) - 5} more")

        # Look up priorities
        all_experiments = CHRONOLOGICAL_EXPERIMENTS + HIGH_REG_EXPERIMENTS
        priority_map = {cfg.replace(".yaml", ""): pri for cfg, pri in all_experiments}

        for config, seed in failed:
            priority = priority_map.get(config, 0)
            jobs_to_submit.append((config, seed, priority))

    elif args.configs:
        # Submit specific configs with specified seeds
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

            for seed in seeds:
                jobs_to_submit.append((config_clean, seed, priority))

    else:
        # Submit experiment sets
        experiments = []

        if args.experiment_type == "chrono" or args.experiment_type == "both":
            seeds = args.seeds if args.seeds else [0, 1, 2]
            experiments.extend(
                [
                    (cfg.replace(".yaml", ""), seed, pri)
                    for cfg, pri in CHRONOLOGICAL_EXPERIMENTS
                    for seed in seeds
                ]
            )

        if args.experiment_type == "high-reg" or args.experiment_type == "both":
            seeds = args.seeds if args.seeds else [0, 1, 2, 3, 4]
            experiments.extend(
                [
                    (cfg.replace(".yaml", ""), seed, pri)
                    for cfg, pri in HIGH_REG_EXPERIMENTS
                    for seed in seeds
                ]
            )

        if not args.experiment_type:
            print("Please specify --experiment-type or --configs")
            return 1

        jobs_to_submit = experiments

    # Pre-validation
    print("🔍 Validating configuration files...")
    configs_to_check = list(set(job[0] + ".yaml" for job in jobs_to_submit))
    missing_configs = []

    for config in configs_to_check:
        if not submitter.validate_config(f"exp_configs/{config}"):
            missing_configs.append(config)

    if missing_configs:
        print("\n❌ Missing config files:")
        for config in missing_configs:
            print(f"  - {config}")
        print("\nPlease ensure all config files exist before submission.")
        return 1

    print(f"✅ All {len(configs_to_check)} config files validated!")

    # Check existing jobs
    existing_jobs = set()
    if args.skip_existing and not args.force:
        print("\n🔍 Checking for existing jobs...")
        existing_jobs = submitter.check_existing_jobs()
        if existing_jobs:
            print(f"Found {len(existing_jobs)} existing jobs.")

    # Filter out existing jobs
    filtered_jobs = []
    skipped = 0
    for config, seed, priority in jobs_to_submit:
        if args.force or (config, seed) not in existing_jobs:
            filtered_jobs.append((config, seed, priority))
        else:
            skipped += 1

    if not filtered_jobs:
        print("\n✅ All jobs already exist! Nothing to submit.")
        return 0

    # Show summary
    print("\n📊 Submission Summary:")
    print(f"  Total jobs requested: {len(jobs_to_submit)}")
    if skipped > 0:
        print(f"  Existing jobs to skip: {skipped}")
    print(f"  New jobs to submit: {len(filtered_jobs)}")

    # Show first few jobs as preview
    print("\n  First few jobs:")
    for config, seed, priority in filtered_jobs[:3]:
        print(f"    - {config}, seed={seed}, priority={priority}")
    if len(filtered_jobs) > 3:
        print(f"    ... and {len(filtered_jobs) - 3} more")

    if args.dry_run:
        print("\n🚀 DRY RUN MODE - No jobs will actually be submitted")
        print("\nWould submit the following jobs:")
        for i, (config, seed, priority) in enumerate(filtered_jobs, 1):
            print(f"  [{i}] {config}, seed={seed}, priority={priority}")
        return 0

    # Confirmation
    if not args.no_confirm and len(filtered_jobs) > 10:
        response = input(
            f"\n⚠️  About to submit {len(filtered_jobs)} jobs. Continue? [y/N]: "
        )
        if response.lower() != "y":
            print("Aborted.")
            return 0

    # Submit jobs
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

    # Print summary
    print(
        f"\n📈 Results: {successful}/{len(filtered_jobs)} jobs submitted successfully"
    )

    if successful > 0:
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

    return 0 if successful == len(filtered_jobs) else 1


if __name__ == "__main__":
    sys.exit(main())
