#!/usr/bin/env python3
"""Analyze correlations between regression fit metrics and final validation accuracy.

This version properly handles multiple hyperparameter variations of the same config.
"""

import json
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
from collections import defaultdict
import argparse
from typing import Dict, List, Tuple


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
    # Default values based on typical settings
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


def fit_regression(
    epochs: np.ndarray, losses: np.ndarray
) -> Tuple[float, float, float]:
    """Fit linear regression to log(epoch) vs loss."""
    # Use log(epoch + 1) to handle epoch 0
    log_epochs = np.log(epochs + 1)

    # Fit linear regression
    slope, intercept = np.polyfit(log_epochs, losses, 1)

    # Calculate R² and RMSE
    predictions = slope * log_epochs + intercept
    ss_res = np.sum((losses - predictions) ** 2)
    ss_tot = np.sum((losses - np.mean(losses)) ** 2)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    rmse = np.sqrt(np.mean((losses - predictions) ** 2))

    return slope, r_squared, rmse


def analyze_config_regression(config_runs: List[Dict]) -> Dict:
    """Analyze regression metrics for a configuration across multiple seeds."""
    # Collect metrics across seeds
    all_train_slopes = []
    all_train_r2s = []
    all_train_rmses = []
    all_val_slopes = []
    all_val_r2s = []
    all_val_rmses = []
    all_final_val_accs = []

    for run in config_runs:
        metrics = run["metrics"]

        # Extract loss curves
        epochs = np.array([m["epoch"] for m in metrics])
        train_losses = np.array([m["train_loss"] for m in metrics])
        val_losses = np.array([m["val_loss"] for m in metrics])

        # Fit regressions
        train_slope, train_r2, train_rmse = fit_regression(epochs, train_losses)
        val_slope, val_r2, val_rmse = fit_regression(epochs, val_losses)

        # Get final validation accuracy
        final_val_acc = run["final_metrics"].get("val_acc", metrics[-1]["val_acc"])

        all_train_slopes.append(train_slope)
        all_train_r2s.append(train_r2)
        all_train_rmses.append(train_rmse)
        all_val_slopes.append(val_slope)
        all_val_r2s.append(val_r2)
        all_val_rmses.append(val_rmse)
        all_final_val_accs.append(final_val_acc)

    # Return averaged metrics
    return {
        "train_slope": np.mean(all_train_slopes),
        "train_r2": np.mean(all_train_r2s),
        "train_rmse": np.mean(all_train_rmses),
        "val_slope": np.mean(all_val_slopes),
        "val_r2": np.mean(all_val_r2s),
        "val_rmse": np.mean(all_val_rmses),
        "final_val_acc": np.mean(all_final_val_accs),
        "num_seeds": len(config_runs),
    }


def create_correlation_plots(
    df: pd.DataFrame, output_path: Path, include_labels: bool = True
):
    """Create correlation plots between regression metrics and final validation accuracy."""
    fig, axes = plt.subplots(3, 3, figsize=(15, 15))
    fig.suptitle("Regression Metrics vs Final Validation Accuracy", fontsize=16)

    # Metrics to plot
    metrics = [
        ("train_slope", "Training Loss Slope"),
        ("train_r2", "Training Loss R²"),
        ("train_rmse", "Training Loss RMSE"),
    ]

    # Plot training metrics vs final val acc
    for i, (metric, label) in enumerate(metrics):
        ax = axes[0, i]

        # Calculate correlation
        corr, p_value = stats.pearsonr(df[metric], df["final_val_acc"])

        # Create scatter plot
        scatter = ax.scatter(
            df[metric],
            df["final_val_acc"],
            c=df.index,
            cmap="viridis",
            s=100,
            alpha=0.7,
        )

        # Add regression line
        z = np.polyfit(df[metric], df["final_val_acc"], 1)
        p = np.poly1d(z)
        x_line = np.linspace(df[metric].min(), df[metric].max(), 100)
        ax.plot(x_line, p(x_line), "r--", alpha=0.8, linewidth=2)

        # Add labels for points if requested
        if include_labels:
            for idx, row in df.iterrows():
                config_label = row["config"]
                # Shorten long labels
                if len(config_label) > 20:
                    parts = config_label.split("_")
                    if "lr" in config_label:
                        # Keep step and lr info
                        config_label = "_".join(
                            [
                                p
                                for p in parts
                                if "step" in p or "lr" in p or "controlled" in p
                            ]
                        )
                ax.annotate(
                    config_label,
                    (row[metric], row["final_val_acc"]),
                    fontsize=8,
                    alpha=0.7,
                    rotation=45,
                )

        ax.set_xlabel(label)
        ax.set_ylabel("Final Val Accuracy")
        ax.set_title(f"r = {corr:.3f}, p = {p_value:.3f}")
        ax.grid(True, alpha=0.3)

    # Plot validation metrics vs final val acc
    val_metrics = [
        ("val_slope", "Validation Loss Slope"),
        ("val_r2", "Validation Loss R²"),
        ("val_rmse", "Validation Loss RMSE"),
    ]

    for i, (metric, label) in enumerate(val_metrics):
        ax = axes[1, i]

        # Calculate correlation
        corr, p_value = stats.pearsonr(df[metric], df["final_val_acc"])

        # Create scatter plot
        scatter = ax.scatter(
            df[metric],
            df["final_val_acc"],
            c=df.index,
            cmap="viridis",
            s=100,
            alpha=0.7,
        )

        # Add regression line
        z = np.polyfit(df[metric], df["final_val_acc"], 1)
        p = np.poly1d(z)
        x_line = np.linspace(df[metric].min(), df[metric].max(), 100)
        ax.plot(x_line, p(x_line), "r--", alpha=0.8, linewidth=2)

        # Add labels for points if requested
        if include_labels:
            for idx, row in df.iterrows():
                config_label = row["config"]
                if len(config_label) > 20:
                    parts = config_label.split("_")
                    config_label = "_".join(
                        [
                            p
                            for p in parts
                            if "step" in p or "lr" in p or "controlled" in p
                        ]
                    )
                ax.annotate(
                    config_label,
                    (row[metric], row["final_val_acc"]),
                    fontsize=8,
                    alpha=0.7,
                    rotation=45,
                )

        ax.set_xlabel(label)
        ax.set_ylabel("Final Val Accuracy")
        ax.set_title(f"r = {corr:.3f}, p = {p_value:.3f}")
        ax.grid(True, alpha=0.3)

    # Plot train vs val metrics
    train_val_pairs = [
        ("train_slope", "val_slope", "Slope"),
        ("train_r2", "val_r2", "R²"),
        ("train_rmse", "val_rmse", "RMSE"),
    ]

    for i, (train_metric, val_metric, label) in enumerate(train_val_pairs):
        ax = axes[2, i]

        # Calculate correlation
        corr, p_value = stats.pearsonr(df[train_metric], df[val_metric])

        # Create scatter plot
        scatter = ax.scatter(
            df[train_metric],
            df[val_metric],
            c=df["final_val_acc"],
            cmap="RdYlGn",
            s=100,
            alpha=0.7,
        )

        # Add regression line
        z = np.polyfit(df[train_metric], df[val_metric], 1)
        p = np.poly1d(z)
        x_line = np.linspace(df[train_metric].min(), df[train_metric].max(), 100)
        ax.plot(x_line, p(x_line), "r--", alpha=0.8, linewidth=2)

        # Add colorbar
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label("Final Val Acc", rotation=270, labelpad=15)

        ax.set_xlabel(f"Training {label}")
        ax.set_ylabel(f"Validation {label}")
        ax.set_title(f"r = {corr:.3f}, p = {p_value:.3f}")
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze regression correlations with hyperparameter handling"
    )
    parser.add_argument(
        "--base-path", type=str, default=".", help="Base path for experiments"
    )
    parser.add_argument("--experiment", type=str, required=True, help="Experiment name")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="correlation_analysis",
        help="Output directory",
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

    # Analyze each configuration
    results = []
    for config_id, runs in config_results.items():
        print(f"Analyzing {config_id} ({len(runs)} seeds)...")
        analysis = analyze_config_regression(runs)
        analysis["config"] = config_id
        results.append(analysis)

    # Create DataFrame and sort by final validation accuracy
    df = pd.DataFrame(results)
    df = df.sort_values("final_val_acc", ascending=False)

    # Save summary
    summary_path = output_dir / "regression_analysis_summary_v2.csv"
    df.to_csv(summary_path, index=False)
    print(f"\nSaved summary to {summary_path}")

    # Create plots with labels
    plot_path_labeled = output_dir / "regression_correlation_analysis_v2_labeled.png"
    create_correlation_plots(df, plot_path_labeled, include_labels=True)
    print(f"Saved labeled plots to {plot_path_labeled}")

    # Create plots without labels
    plot_path_unlabeled = (
        output_dir / "regression_correlation_analysis_v2_unlabeled.png"
    )
    create_correlation_plots(df, plot_path_unlabeled, include_labels=False)
    print(f"Saved unlabeled plots to {plot_path_unlabeled}")

    # Print summary statistics
    print("\nTop 10 configurations by validation accuracy:")
    print(
        df[["config", "final_val_acc", "val_slope", "val_r2"]]
        .head(10)
        .to_string(index=False)
    )

    print("\nCorrelation summary:")
    for metric in [
        "train_slope",
        "train_r2",
        "train_rmse",
        "val_slope",
        "val_r2",
        "val_rmse",
    ]:
        corr, p_value = stats.pearsonr(df[metric], df["final_val_acc"])
        print(f"{metric}: r = {corr:.3f}, p = {p_value:.3f}")


if __name__ == "__main__":
    main()
