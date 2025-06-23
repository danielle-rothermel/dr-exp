#!/usr/bin/env python3
"""Create a CSV with mean loss and accuracy per epoch for each configuration."""

import json
from pathlib import Path
import pandas as pd
import numpy as np
from collections import defaultdict
import argparse
from typing import Dict, List


def get_config_identifier(job: Dict) -> str:
    """Create a unique identifier for a configuration including hyperparameter variations."""
    config = job["config"]
    config_name = config.get("run_name", config.get("config_name", "unknown"))

    # Remove _high_reg suffix if present
    base_name = config_name.replace("_high_reg", "")

    # Check if we have tags that indicate a sweep
    tags = job.get("tags", [])

    # For tagged sweeps, create identifier from tags
    if tags:
        # Look for lr tags
        lr_tag = next((tag for tag in tags if tag.startswith("lr-")), None)
        wd_tag = next((tag for tag in tags if tag.startswith("wd-")), None)

        if lr_tag or wd_tag:
            parts = [base_name]
            if lr_tag:
                parts.append(lr_tag)
            if wd_tag:
                parts.append(wd_tag)
            return "_".join(parts)

    # For untagged jobs, check if hyperparameters differ from defaults
    lr = config.get("optim", {}).get("lr", None)
    wd = config.get("optim", {}).get("weight_decay", None)

    # Build identifier with significant hyperparameters
    if base_name.startswith("step00") or base_name.startswith("controlled_adamw"):
        # AdamW configs
        if lr and lr != 0.001:  # Default AdamW lr
            base_name += f"_lr{lr}"
        if wd and wd != 0.01:  # Default AdamW wd
            base_name += f"_wd{wd}"
    elif (
        "sgd" in base_name
        or base_name.startswith("step01")
        or base_name.startswith("controlled")
    ):
        # SGD configs
        if lr and lr != 0.1:  # Default SGD lr
            base_name += f"_lr{lr}"
        if wd and wd != 0.0005:  # Default SGD wd
            base_name += f"_wd{wd}"

    return base_name


def renumber_step_name(step_name: str) -> str:
    """Renumber step names to account for removed steps."""
    # Mapping to renumber steps after removing 8-10
    renumber_map = {
        "step11": "step08",
        "step12": "step09",
        "step13": "step10",
        "step14": "step11",
        "step15": "step12",
        "step16": "step13",
        "step17": "step14",
    }

    for old, new in renumber_map.items():
        if old in step_name:
            step_name = step_name.replace(old, new)

    return step_name


def load_experiment_data(exp_dir: Path) -> Dict[str, List[Dict]]:
    """Load all experiment data grouped by configuration identifier."""
    jobs_dir = exp_dir / "jobs"
    storage_dir = exp_dir / "storage"

    # Group results by configuration identifier
    config_results = defaultdict(list)

    for job_file in jobs_dir.glob("*.json"):
        with open(job_file) as f:
            job = json.load(f)

        # Skip if not completed
        if job["status"] != "completed":
            continue

        # Skip steps 8-10 (originally 11-13 before renumbering)
        config_name = job["config"].get(
            "run_name", job["config"].get("config_name", "unknown")
        )
        if any(
            skip in config_name
            for skip in [
                "step08_lrn_dropout",
                "step09_xavier",
                "step10_no_lrn",
                "step11_resnet12",
                "step12_alexnet",
                "step13_no_dropout",
            ]
        ):
            continue

        # Get unique identifier
        config_id = get_config_identifier(job)
        config_id = renumber_step_name(config_id)

        # Load metrics
        run_dir = storage_dir / f"run_{job['id']}"
        metrics_file = run_dir / "metrics.jsonl"
        metrics_json_file = run_dir / "metrics.json"

        metrics = []
        if metrics_file.exists():
            # Read JSONL file
            with open(metrics_file) as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        # Extract the metrics from the nested structure
                        if "metrics" in entry:
                            metrics.append(entry["metrics"])
                        else:
                            metrics.append(entry)
        elif metrics_json_file.exists():
            # Fallback to JSON file if it exists
            with open(metrics_json_file) as f:
                metrics = json.load(f)

        if metrics:
            result = {
                "job_id": job["id"],
                "config_id": config_id,
                "seed": job["config"].get("seed", -1),
                "metrics": metrics,
                "final_metrics": job.get("final_metrics", {}),
                "tags": job.get("tags", []),
            }

            config_results[config_id].append(result)

    return dict(config_results)


def aggregate_metrics_by_epoch(config_runs: List[Dict]) -> pd.DataFrame:
    """Aggregate metrics across seeds for each epoch."""
    # Find max epochs
    max_epochs = max(len(run["metrics"]) for run in config_runs)

    # Initialize collectors
    epoch_data = []

    for epoch in range(max_epochs):
        train_losses = []
        val_losses = []
        train_accs = []
        val_accs = []

        for run in config_runs:
            if epoch < len(run["metrics"]):
                metrics = run["metrics"][epoch]
                train_losses.append(metrics.get("train_loss", np.nan))
                val_losses.append(metrics.get("val_loss", np.nan))
                train_accs.append(metrics.get("train_acc", np.nan))
                val_accs.append(metrics.get("val_acc", np.nan))

        if train_losses:  # Only add if we have data
            epoch_data.append(
                {
                    "epoch": epoch,
                    "train_loss_mean": np.nanmean(train_losses),
                    "train_loss_std": np.nanstd(train_losses),
                    "val_loss_mean": np.nanmean(val_losses),
                    "val_loss_std": np.nanstd(val_losses),
                    "train_acc_mean": np.nanmean(train_accs),
                    "train_acc_std": np.nanstd(train_accs),
                    "val_acc_mean": np.nanmean(val_accs),
                    "val_acc_std": np.nanstd(val_accs),
                    "num_seeds": len([x for x in train_losses if not np.isnan(x)]),
                }
            )

    return pd.DataFrame(epoch_data)


def create_epoch_metrics_csv(config_results: Dict[str, List[Dict]], output_path: Path):
    """Create CSV with epoch-wise metrics for all configurations."""
    all_data = []

    for config_id, runs in sorted(config_results.items()):
        print(f"Processing {config_id} ({len(runs)} seeds)...")

        # Get aggregated metrics
        epoch_df = aggregate_metrics_by_epoch(runs)

        # Add config identifier to each row
        epoch_df["config"] = config_id

        # Get final validation accuracy (for reference)
        final_val_accs = []
        for run in runs:
            final_val_acc = run["final_metrics"].get(
                "val_acc", run["metrics"][-1]["val_acc"]
            )
            final_val_accs.append(final_val_acc)
        epoch_df["final_val_acc"] = np.mean(final_val_accs)

        all_data.append(epoch_df)

    # Combine all configs
    full_df = pd.concat(all_data, ignore_index=True)

    # Reorder columns
    column_order = [
        "config",
        "epoch",
        "train_loss_mean",
        "train_loss_std",
        "val_loss_mean",
        "val_loss_std",
        "train_acc_mean",
        "train_acc_std",
        "val_acc_mean",
        "val_acc_std",
        "num_seeds",
        "final_val_acc",
    ]
    full_df = full_df[column_order]

    # Save to CSV
    full_df.to_csv(output_path, index=False)
    print(f"\nSaved epoch metrics to {output_path}")

    # Print summary
    configs = full_df["config"].unique()
    print(f"Total configurations: {len(configs)}")
    print(f"Total rows: {len(full_df)}")

    # Show sample
    print("\nSample of data (first 5 rows):")
    print(full_df.head().to_string(index=False))

    return full_df


def create_wide_format_csv(config_results: Dict[str, List[Dict]], output_path: Path):
    """Create wide-format CSV with one row per config and columns for each epoch metric."""
    rows = []

    for config_id, runs in sorted(config_results.items()):
        print(f"Processing {config_id} for wide format...")

        # Get aggregated metrics
        epoch_df = aggregate_metrics_by_epoch(runs)

        # Create wide format row
        row = {"config": config_id}

        # Add metrics for each epoch
        for _, epoch_row in epoch_df.iterrows():
            epoch = int(epoch_row["epoch"])
            row[f"epoch_{epoch}_train_loss"] = epoch_row["train_loss_mean"]
            row[f"epoch_{epoch}_val_loss"] = epoch_row["val_loss_mean"]
            row[f"epoch_{epoch}_train_acc"] = epoch_row["train_acc_mean"]
            row[f"epoch_{epoch}_val_acc"] = epoch_row["val_acc_mean"]

        # Add final metrics
        final_val_accs = []
        for run in runs:
            final_val_acc = run["final_metrics"].get(
                "val_acc", run["metrics"][-1]["val_acc"]
            )
            final_val_accs.append(final_val_acc)
        row["final_val_acc"] = np.mean(final_val_accs)
        row["num_seeds"] = len(runs)
        row["num_epochs"] = len(epoch_df)

        rows.append(row)

    # Create DataFrame
    wide_df = pd.DataFrame(rows)

    # Sort by final validation accuracy
    wide_df = wide_df.sort_values("final_val_acc", ascending=False)

    # Save to CSV
    wide_df.to_csv(output_path, index=False)
    print(f"\nSaved wide-format epoch metrics to {output_path}")

    return wide_df


def main():
    parser = argparse.ArgumentParser(description="Create CSV with epoch-wise metrics")
    parser.add_argument(
        "--base-path", type=str, default=".", help="Base path for experiments"
    )
    parser.add_argument("--experiment", type=str, required=True, help="Experiment name")
    parser.add_argument(
        "--output-dir", type=str, default="na_full_t1", help="Output directory"
    )
    args = parser.parse_args()

    # Setup paths
    exp_dir = Path(args.base_path) / args.experiment
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load experiment data
    print(f"Loading experiment data from {exp_dir}...")
    config_results = load_experiment_data(exp_dir)
    print(f"Found {len(config_results)} unique configurations")

    # Create long format CSV (one row per config-epoch combination)
    long_output_path = output_dir / "epoch_metrics_long_format.csv"
    long_df = create_epoch_metrics_csv(config_results, long_output_path)

    # Create wide format CSV (one row per config, columns for each epoch)
    wide_output_path = output_dir / "epoch_metrics_wide_format.csv"
    wide_df = create_wide_format_csv(config_results, wide_output_path)

    print("\nCreated two CSV formats:")
    print(f"1. Long format: {long_output_path}")
    print("   - One row per config-epoch combination")
    print("   - Easier for plotting with libraries like seaborn")
    print(f"2. Wide format: {wide_output_path}")
    print("   - One row per config, columns for each epoch metric")
    print("   - Easier for comparing specific epochs across configs")


if __name__ == "__main__":
    main()
