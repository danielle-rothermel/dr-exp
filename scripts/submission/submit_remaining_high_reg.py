#!/usr/bin/env python3
"""Submit remaining high regularization experiment jobs."""

import subprocess
import time
from pathlib import Path

# Experiment configuration
EXP_DIR = Path("/scratch/ddr8143/repos/dr_exp/high_regularization_ablation")
CONFIG_DIR = Path("/scratch/ddr8143/repos/dr_exp/exp_configs")

# Check which jobs need to be submitted
# We have 12 submitted, need 13 more to reach 25 total

# Remaining configs to submit (step02 seed 2-4, step03 all, step04 all)
remaining_jobs = [
    ("step02_no_randaug_high_reg.yaml", 2, 78),
    ("step02_no_randaug_high_reg.yaml", 3, 77),
    ("step02_no_randaug_high_reg.yaml", 4, 76),
    ("step03_no_cutmix_high_reg.yaml", 0, 70),
    ("step03_no_cutmix_high_reg.yaml", 1, 69),
    ("step03_no_cutmix_high_reg.yaml", 2, 68),
    ("step03_no_cutmix_high_reg.yaml", 3, 67),
    ("step03_no_cutmix_high_reg.yaml", 4, 66),
    ("step04_no_mixup_high_reg.yaml", 0, 60),
    ("step04_no_mixup_high_reg.yaml", 1, 59),
    ("step04_no_mixup_high_reg.yaml", 2, 58),
    ("step04_no_mixup_high_reg.yaml", 3, 57),
    ("step04_no_mixup_high_reg.yaml", 4, 56),
]


def submit_job(config_name: str, seed: int, priority: int) -> bool | None:
    """Submit a single job."""
    cmd = [
        "uv",
        "run",
        "dr_exp",
        "--base-path",
        str(EXP_DIR),
        "--experiment",
        "main",
        "job",
        "submit",
        "--config-path",
        str(CONFIG_DIR),
        "--config-name",
        config_name,
        "--priority",
        str(priority),
        "--overrides",
        f"seed={seed}",
    ]

    print(f"Submitting: {config_name} with seed={seed}, priority={priority}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)  # noqa: S603
        print(f"  ✓ Success: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Failed: {e.stderr}")
        return False


def main() -> None:
    """Submit remaining jobs."""
    print("=== Submitting Remaining High Regularization Jobs ===")
    print(f"Jobs to submit: {len(remaining_jobs)}")
    print()

    submitted = 0
    failed = 0

    for config, seed, priority in remaining_jobs:
        if submit_job(config, seed, priority):
            submitted += 1
        else:
            failed += 1

        # Small delay to avoid overwhelming the system
        time.sleep(2)

    print("\n=== Submission Complete ===")
    print(f"Successfully submitted: {submitted}")
    print(f"Failed: {failed}")

    # Show status
    print("\nChecking experiment status...")
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "uv",
            "run",
            "dr_exp",
            "--base-path",
            str(EXP_DIR),
            "--experiment",
            "main",
            "status",
        ],
        check=False,
    )


if __name__ == "__main__":
    main()
