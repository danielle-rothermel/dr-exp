#!/usr/bin/env python3
"""Create CSV with metrics for all epochs for each configuration."""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Any


def load_metrics(metrics_file: Path) -> List[Dict]:
    """Load metrics from a JSONL file."""
    metrics = []
    with open(metrics_file, "r") as f:
        for line in f:
            data = json.loads(line.strip())
            if "metrics" in data:
                metrics.append(data["metrics"])
            else:
                metrics.append(data)
    return metrics


def get_config_changes(config_name: str) -> Dict[str, Any]:
    """Extract what changed from baseline for each config."""
    changes = {
        "step00_baseline": {},
        "step01_sgd": {"optimizer": "sgd"},
        "step02_no_randaug": {"randaugment": False},
        "step03_no_cutmix": {"cutmix": False},
        "step04_no_mixup": {"mixup": False},
        "step05_no_warmup": {"warmup": False},
        "step06_steplr": {"lr_scheduler": "step"},
        "step07_no_residual": {"residual": False},
        "step08_lrn_dropout": {"normalization": "lrn+dropout"},
        "step09_xavier": {"init": "xavier"},
        "step10_no_lrn": {"init": "xavier", "normalization": "none"},
        "step11_resnet12": {
            "init": "xavier",
            "normalization": "none",
            "model": "resnet12",
        },
        "step12_alexnet": {
            "init": "xavier",
            "normalization": "none",
            "model": "alexnet",
        },
        "step13_no_dropout": {"dropout": False},
        "step14_tanh": {"activation": "tanh"},
        "step15_no_colorjitter": {"colorjitter": False},
        "step16_no_rrc": {"random_resized_crop": False},
        "step17_no_hflip": {"horizontal_flip": False},
    }

    base_name = config_name.replace("_high_reg", "")
    return changes.get(base_name, {})


def should_include_config(config_name: str) -> bool:
    """Check if config should be included (filter out steps 8-10)."""
    base_name = config_name.replace("_high_reg", "")
    excluded_steps = ["step08_lrn_dropout", "step09_xavier", "step10_no_lrn"]
    return base_name not in excluded_steps


def renumber_step_name(config_name: str) -> str:
    """Renumber steps to remove gaps after filtering steps 8-10."""
    renumber_map = {
        "step00": "step00",
        "step01": "step01",
        "step02": "step02",
        "step03": "step03",
        "step04": "step04",
        "step05": "step05",
        "step06": "step06",
        "step07": "step07",
        "step11": "step08",
        "step12": "step09",
        "step13": "step10",
        "step14": "step11",
        "step15": "step12",
        "step16": "step13",
        "step17": "step14",
    }

    for old_step, new_step in renumber_map.items():
        if config_name.startswith(old_step):
            return config_name.replace(old_step, new_step, 1)

    return config_name


def collect_experiment_data(base_path: Path, experiment: str) -> pd.DataFrame:
    """Collect all experiment data with metrics for all epochs."""
    exp_dir = base_path / experiment
    storage_dir = exp_dir / "storage"

    # Store all rows for the dataframe
    all_rows = []

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
        config_name = job["config"].get(
            "run_name", job["config"].get("config_name", "unknown")
        )

        # Skip excluded configs
        if not should_include_config(config_name):
            continue

        # Load metrics
        metrics_file = run_dir / "metrics.jsonl"
        if not metrics_file.exists():
            continue

        metrics = load_metrics(metrics_file)
        if not metrics:
            continue

        # Get seed from config
        seed = job["config"].get("seed", -1)

        # Renumber the config name for display
        display_name = renumber_step_name(config_name)

        # Get config changes
        changes = get_config_changes(config_name)

        # Create a row for each epoch
        for epoch_idx, metric in enumerate(metrics):
            row = {
                "job_id": job_id,
                "config": display_name,
                "original_config": config_name,
                "seed": seed,
                "epoch": epoch_idx,
                "train_loss": metric.get("train_loss", np.nan),
                "train_acc": metric.get("train_acc", np.nan),
                "val_loss": metric.get("val_loss", np.nan),
                "val_acc": metric.get("val_acc", np.nan),
            }

            # Add config changes as columns
            for key, value in changes.items():
                row[f"change_{key}"] = value

            all_rows.append(row)

    # Create dataframe
    df = pd.DataFrame(all_rows)

    # Sort by config, seed, and epoch
    df = df.sort_values(["config", "seed", "epoch"])

    return df


def create_summary_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Create a summary dataframe with mean and std across seeds for each config/epoch."""
    # Group by config and epoch, calculate statistics
    summary = (
        df.groupby(["config", "epoch"])
        .agg(
            {
                "train_loss": ["mean", "std", "count"],
                "train_acc": ["mean", "std"],
                "val_loss": ["mean", "std"],
                "val_acc": ["mean", "std"],
            }
        )
        .reset_index()
    )

    # Flatten column names
    summary.columns = [
        "config",
        "epoch",
        "train_loss_mean",
        "train_loss_std",
        "num_seeds",
        "train_acc_mean",
        "train_acc_std",
        "val_loss_mean",
        "val_loss_std",
        "val_acc_mean",
        "val_acc_std",
    ]

    # Add config changes
    config_changes = {}
    for config in df["config"].unique():
        original = df[df["config"] == config]["original_config"].iloc[0]
        changes = get_config_changes(original)
        config_changes[config] = changes

    # Add change columns to summary
    for config, changes in config_changes.items():
        mask = summary["config"] == config
        for key, value in changes.items():
            summary.loc[mask, f"change_{key}"] = value

    return summary


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Create CSV with all epoch metrics")
    parser.add_argument("--base-path", type=Path, default=Path("./experiment"))
    parser.add_argument("--experiment", type=str, default="test")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("./full_metrics_output")
    )

    args = parser.parse_args()

    print(f"Analyzing experiments in {args.base_path / args.experiment}")

    # Collect data
    df = collect_experiment_data(args.base_path, args.experiment)

    if df.empty:
        print("No data found!")
        return

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Save full data (all seeds, all epochs)
    full_csv_path = args.output_dir / "full_metrics_all_seeds.csv"
    df.to_csv(full_csv_path, index=False, float_format="%.6f")
    print(f"\nSaved full metrics (all seeds) to {full_csv_path}")
    print(f"  Shape: {df.shape}")
    print(f"  Configs: {df['config'].nunique()}")
    print(f"  Total rows: {len(df)}")

    # Create and save summary statistics
    summary_df = create_summary_stats(df)
    summary_csv_path = args.output_dir / "metrics_summary_by_epoch.csv"
    summary_df.to_csv(summary_csv_path, index=False, float_format="%.6f")
    print(f"\nSaved summary metrics (mean/std across seeds) to {summary_csv_path}")
    print(f"  Shape: {summary_df.shape}")

    # Create a pivot table for easier analysis (configs as rows, epochs as columns)
    # Just for validation accuracy as an example
    pivot_val_acc = summary_df.pivot(
        index="config", columns="epoch", values="val_acc_mean"
    )
    pivot_csv_path = args.output_dir / "val_acc_pivot_table.csv"
    pivot_val_acc.to_csv(pivot_csv_path, float_format="%.4f")
    print(f"\nSaved validation accuracy pivot table to {pivot_csv_path}")

    # Print sample of the data
    print("\nSample of full data (first 10 rows):")
    print(df.head(10).to_string(index=False))

    print("\nSample of summary data (first 10 rows):")
    print(summary_df.head(10).to_string(index=False))

    # Print config counts
    print("\nRows per config:")
    config_counts = df.groupby("config").size().sort_index()
    for config, count in config_counts.items():
        seeds = df[df["config"] == config]["seed"].nunique()
        epochs = df[df["config"] == config]["epoch"].nunique()
        print(f"  {config}: {count} rows ({seeds} seeds × {epochs} epochs)")


if __name__ == "__main__":
    main()
