#!/usr/bin/env python3
"""Analyze which experiment configurations failed to make training progress."""

import json
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np


def load_metrics(metrics_file: Path) -> List[Dict]:
    """Load metrics from a JSONL file."""
    metrics = []
    with open(metrics_file, "r") as f:
        for line in f:
            metrics.append(json.loads(line.strip()))
    return metrics


def analyze_no_progress_configs(
    base_path: Path, experiment: str
) -> Dict[str, List[Tuple[str, float, float]]]:
    """Find configs that made no progress in training.

    Returns dict mapping config names to list of (job_id, final_val_acc, max_val_acc) tuples.
    """
    exp_dir = base_path / experiment
    storage_dir = exp_dir / "storage"

    no_progress_configs = {}

    # Analyze each completed job
    for run_dir in storage_dir.glob("run_*"):
        if not run_dir.is_dir():
            continue

        job_id = run_dir.name.replace("run_", "")

        # Load job config
        job_file = exp_dir / "jobs" / f"{job_id}.json"
        if not job_file.exists():
            continue

        with open(job_file, "r") as f:
            job = json.load(f)

        if job["status"] != "completed":
            continue

        # Get config name
        config_name = job["config"].get("config_name", "unknown")

        # Load metrics
        metrics_file = run_dir / "metrics.jsonl"
        if not metrics_file.exists():
            continue

        metrics = load_metrics(metrics_file)

        # Extract validation accuracies
        val_accs = [m["val_acc"] for m in metrics if "val_acc" in m]

        if not val_accs:
            continue

        # Check if model made progress
        # For CIFAR-10, random chance is 0.1 (10%)
        final_val_acc = val_accs[-1] if val_accs else 0.0
        max_val_acc = max(val_accs) if val_accs else 0.0

        # Consider no progress if max accuracy is below 15% (just above random)
        if max_val_acc < 0.15:
            if config_name not in no_progress_configs:
                no_progress_configs[config_name] = []
            no_progress_configs[config_name].append(
                (job_id, final_val_acc, max_val_acc)
            )

    return no_progress_configs


def main():
    """Main analysis function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Find configs that made no training progress"
    )
    parser.add_argument("--base-path", type=Path, default=Path("./experiment"))
    parser.add_argument("--experiment", type=str, default="test")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.15,
        help="Max accuracy threshold below which to consider no progress (default: 0.15)",
    )

    args = parser.parse_args()

    print(f"Analyzing experiments in {args.base_path / args.experiment}")
    print(f"Looking for configs with max validation accuracy < {args.threshold:.1%}")
    print()

    no_progress = analyze_no_progress_configs(args.base_path, args.experiment)

    if not no_progress:
        print("All configs made reasonable training progress!")
        return

    print("Configs that made NO training progress:\n")

    for config_name, jobs in sorted(no_progress.items()):
        print(f"{config_name}:")
        print(f"  Failed runs: {len(jobs)}")

        # Calculate average max accuracy across seeds
        max_accs = [max_acc for _, _, max_acc in jobs]
        avg_max_acc = np.mean(max_accs)

        print(f"  Average max accuracy: {avg_max_acc:.1%}")
        print("  Individual runs:")

        for job_id, final_acc, max_acc in jobs:
            print(f"    {job_id[:8]}: final={final_acc:.1%}, max={max_acc:.1%}")
        print()

    # Summary
    print(f"\nTotal configs with no progress: {len(no_progress)}")
    total_failed_runs = sum(len(jobs) for jobs in no_progress.values())
    print(f"Total failed runs: {total_failed_runs}")


if __name__ == "__main__":
    main()
