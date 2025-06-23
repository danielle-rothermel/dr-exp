#!/usr/bin/env python3
"""Submit high regularization ablation experiment jobs."""

import subprocess
import time
from pathlib import Path

# Experiment configuration
EXP_DIR = Path("/scratch/ddr8143/repos/dr_exp/high_regularization_ablation")
CONFIG_DIR = Path("/scratch/ddr8143/repos/dr_exp/exp_configs")

# First 5 configs with high regularization
CONFIGS = [
    "step00_baseline_high_reg.yaml",
    "step01_sgd_high_reg.yaml",
    "step02_no_randaug_high_reg.yaml",
    "step03_no_cutmix_high_reg.yaml",
    "step04_no_mixup_high_reg.yaml",
]

# 5 seeds
SEEDS = [0, 1, 2, 3, 4]


def submit_job(config_name: str, seed: int, priority: int):
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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"  ✓ Success: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Failed: {e.stderr}")
        return False


def main():
    """Submit all jobs for high regularization experiment."""
    print("=== High Regularization Ablation Experiment Submission ===")
    print(f"Experiment directory: {EXP_DIR}")
    print(f"Configs: {len(CONFIGS)}")
    print(f"Seeds: {len(SEEDS)}")
    print(f"Total jobs: {len(CONFIGS) * len(SEEDS)}")
    print()

    submitted = 0
    failed = 0

    # Submit jobs with decreasing priority by config step
    # Higher priority for earlier steps
    for i, config in enumerate(CONFIGS):
        base_priority = 100 - (i * 10)  # 100, 90, 80, 70, 60

        for seed in SEEDS:
            # Add small seed-based priority variation
            priority = base_priority - seed

            if submit_job(config, seed, priority):
                submitted += 1
            else:
                failed += 1

            # Small delay to avoid overwhelming the system
            time.sleep(0.1)

        print()  # Blank line between configs

    print("\n=== Submission Complete ===")
    print(f"Successfully submitted: {submitted}")
    print(f"Failed: {failed}")

    # Show status
    print("\nChecking experiment status...")
    subprocess.run(
        [
            "uv",
            "run",
            "dr_exp",
            "--base-path",
            str(EXP_DIR),
            "--experiment",
            "main",
            "status",
        ]
    )


if __name__ == "__main__":
    main()
