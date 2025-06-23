#!/usr/bin/env python3
"""Sweep over different numbers of early epochs for regression analysis."""

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


def fit_regression_early(
    epochs: np.ndarray, losses: np.ndarray, max_epoch: int
) -> Tuple[float, float, float]:
    """Fit linear regression to log(epoch) vs loss for early epochs only."""
    # Filter to early epochs
    mask = epochs < max_epoch
    epochs = epochs[mask]
    losses = losses[mask]

    if len(epochs) < 2:
        return np.nan, np.nan, np.nan

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


def analyze_config_early_regression(config_runs: List[Dict], max_epoch: int) -> Dict:
    """Analyze early regression metrics for a configuration across multiple seeds."""
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

        # Fit regressions on early epochs only
        train_slope, train_r2, train_rmse = fit_regression_early(
            epochs, train_losses, max_epoch
        )
        val_slope, val_r2, val_rmse = fit_regression_early(
            epochs, val_losses, max_epoch
        )

        # Get final validation accuracy
        final_val_acc = run["final_metrics"].get("val_acc", metrics[-1]["val_acc"])

        if not np.isnan(train_slope):
            all_train_slopes.append(train_slope)
            all_train_r2s.append(train_r2)
            all_train_rmses.append(train_rmse)
            all_val_slopes.append(val_slope)
            all_val_r2s.append(val_r2)
            all_val_rmses.append(val_rmse)
            all_final_val_accs.append(final_val_acc)

    if not all_train_slopes:
        return None

    # Return averaged metrics
    return {
        "train_slope": np.mean(all_train_slopes),
        "train_r2": np.mean(all_train_r2s),
        "train_rmse": np.mean(all_train_rmses),
        "val_slope": np.mean(all_val_slopes),
        "val_r2": np.mean(all_val_r2s),
        "val_rmse": np.mean(all_val_rmses),
        "final_val_acc": np.mean(all_final_val_accs),
        "num_seeds": len(all_train_slopes),
    }


def sweep_early_epochs(
    config_results: Dict[str, List[Dict]], epoch_range: List[int]
) -> Dict[int, pd.DataFrame]:
    """Sweep over different numbers of early epochs and compute correlations."""
    results_by_epoch = {}

    for max_epoch in epoch_range:
        print(f"\nAnalyzing with max_epoch = {max_epoch}...")

        # Analyze each configuration
        results = []
        for config_id, runs in config_results.items():
            analysis = analyze_config_early_regression(runs, max_epoch)
            if analysis:
                analysis["config"] = config_id
                results.append(analysis)

        if results:
            # Create DataFrame and compute correlations
            df = pd.DataFrame(results)
            df = df.sort_values("final_val_acc", ascending=False)
            results_by_epoch[max_epoch] = df

            # Print correlation summary
            print(f"  Found {len(df)} configurations with sufficient data")
            for metric in ["train_slope", "val_slope", "train_r2", "val_r2"]:
                if metric in df.columns:
                    corr, p_value = stats.pearsonr(df[metric], df["final_val_acc"])
                    print(f"  {metric}: r = {corr:.3f}, p = {p_value:.3f}")

    return results_by_epoch


def create_correlation_sweep_plots(
    results_by_epoch: Dict[int, pd.DataFrame], output_path: Path
):
    """Create plots showing how correlations change with different early epoch cutoffs."""
    # Collect correlation data
    metrics = ["train_slope", "train_r2", "val_slope", "val_r2"]
    correlations = {metric: [] for metric in metrics}
    p_values = {metric: [] for metric in metrics}
    epochs_list = sorted(results_by_epoch.keys())

    for epoch in epochs_list:
        df = results_by_epoch[epoch]
        for metric in metrics:
            if (
                metric in df.columns and len(df) > 3
            ):  # Need at least 4 points for correlation
                corr, p_val = stats.pearsonr(df[metric], df["final_val_acc"])
                correlations[metric].append(corr)
                p_values[metric].append(p_val)
            else:
                correlations[metric].append(np.nan)
                p_values[metric].append(np.nan)

    # Create figure with 2x2 subplots
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "Correlation with Final Accuracy vs Number of Early Epochs Used", fontsize=16
    )

    metric_labels = {
        "train_slope": "Training Loss Slope",
        "train_r2": "Training Loss R²",
        "val_slope": "Validation Loss Slope",
        "val_r2": "Validation Loss R²",
    }

    for idx, (metric, ax) in enumerate(zip(metrics, axes.flat)):
        # Plot correlation
        ax.plot(
            epochs_list,
            correlations[metric],
            "o-",
            linewidth=2,
            markersize=8,
            label="Correlation",
        )

        # Highlight significant correlations (p < 0.05)
        significant = [i for i, p in enumerate(p_values[metric]) if p < 0.05]
        if significant:
            sig_epochs = [epochs_list[i] for i in significant]
            sig_corrs = [correlations[metric][i] for i in significant]
            ax.scatter(
                sig_epochs,
                sig_corrs,
                color="red",
                s=100,
                zorder=5,
                label="p < 0.05",
                edgecolors="black",
                linewidth=1,
            )

        # Add zero line
        ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)

        # Styling
        ax.set_xlabel("Number of Early Epochs")
        ax.set_ylabel("Pearson Correlation (r)")
        ax.set_title(metric_labels[metric])
        ax.grid(True, alpha=0.3)
        ax.legend()

        # Set y-axis limits
        ax.set_ylim(-1, 1)

    plt.tight_layout()
    plt.savefig(
        output_path / "correlation_vs_early_epochs.png", dpi=300, bbox_inches="tight"
    )
    plt.close()

    # Create a second plot showing the best metric at each epoch cutoff
    fig, ax = plt.subplots(figsize=(12, 7))

    # Find best metric at each epoch - using the actual correlation value (not absolute)
    best_corrs = []
    best_metrics = []
    best_abs_corrs = []

    for i, epoch in enumerate(epochs_list):
        # Get correlations for this epoch
        epoch_corrs = {}
        for metric in metrics:
            if not np.isnan(correlations[metric][i]):
                # Store actual correlation value and its absolute value
                epoch_corrs[metric] = (
                    correlations[metric][i],
                    abs(correlations[metric][i]),
                )

        if epoch_corrs:
            # Find metric with highest absolute correlation
            best_metric = max(epoch_corrs, key=lambda m: epoch_corrs[m][1])
            best_corrs.append(epoch_corrs[best_metric][0])  # Actual correlation value
            best_abs_corrs.append(epoch_corrs[best_metric][1])  # Absolute value
            best_metrics.append(best_metric)
        else:
            best_corrs.append(0)
            best_abs_corrs.append(0)
            best_metrics.append("none")

    # Plot all points, colored by which metric is strongest
    colors = {
        "train_slope": "blue",
        "train_r2": "cyan",
        "val_slope": "red",
        "val_r2": "orange",
    }

    # Create scatter plot for all points
    for i, (epoch, corr, metric) in enumerate(
        zip(epochs_list, best_corrs, best_metrics)
    ):
        if metric != "none":
            ax.scatter(
                epoch,
                corr,
                color=colors[metric],
                s=120,
                edgecolors="black",
                linewidth=1,
                alpha=0.8,
                zorder=5,
            )

    # Add lines connecting points for each metric type
    for metric in metrics:
        metric_data = [
            (e, c)
            for e, c, m in zip(epochs_list, best_corrs, best_metrics)
            if m == metric
        ]
        if metric_data:
            epochs, corrs = zip(*metric_data)
            ax.plot(epochs, corrs, "--", color=colors[metric], alpha=0.5, linewidth=1)

    # Add legend with custom markers
    legend_elements = [
        plt.scatter(
            [],
            [],
            color=colors[metric],
            s=120,
            edgecolors="black",
            linewidth=1,
            label=metric_labels[metric],
        )
        for metric in metrics
    ]
    ax.legend(handles=legend_elements, loc="best", framealpha=0.9)

    # Add zero line
    ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)

    ax.set_xlabel("Number of Early Epochs", fontsize=12)
    ax.set_ylabel("Correlation with Final Accuracy", fontsize=12)
    ax.set_title("Strongest Predictor at Each Early Epoch Cutoff", fontsize=14)
    ax.grid(True, alpha=0.3)

    # Set y-axis limits to show full correlation range
    ax.set_ylim(-0.8, 0.6)

    plt.tight_layout()
    plt.savefig(
        output_path / "best_predictor_vs_early_epochs.png", dpi=300, bbox_inches="tight"
    )
    plt.close()

    # Create summary table
    summary_data = []
    for epoch in epochs_list:
        row = {"epochs": epoch, "n_configs": len(results_by_epoch[epoch])}
        for metric in metrics:
            row[f"{metric}_r"] = correlations[metric][epochs_list.index(epoch)]
            row[f"{metric}_p"] = p_values[metric][epochs_list.index(epoch)]
        summary_data.append(row)

    summary_df = pd.DataFrame(summary_data)
    summary_df.to_csv(output_path / "early_epochs_sweep_summary.csv", index=False)
    print(f"\nSaved summary to {output_path / 'early_epochs_sweep_summary.csv'}")


def create_heatmap_plot(results_by_epoch: Dict[int, pd.DataFrame], output_path: Path):
    """Create a heatmap showing how each config's metrics change with epoch cutoff."""
    # Get all unique configs
    all_configs = set()
    for df in results_by_epoch.values():
        all_configs.update(df["config"].values)

    # Focus on top performers
    final_accs = {}
    for config in all_configs:
        # Get final accuracy from any epoch's data
        for df in results_by_epoch.values():
            if config in df["config"].values:
                final_accs[config] = df[df["config"] == config]["final_val_acc"].values[
                    0
                ]
                break

    # Get top 15 configs
    top_configs = sorted(final_accs.keys(), key=lambda x: final_accs[x], reverse=True)[
        :15
    ]

    # Create heatmaps for each metric
    metrics = ["val_slope", "val_r2"]
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    for idx, metric in enumerate(metrics):
        # Build matrix
        epochs_list = sorted(results_by_epoch.keys())
        matrix = []

        for config in top_configs:
            row = []
            for epoch in epochs_list:
                df = results_by_epoch[epoch]
                if config in df["config"].values:
                    value = df[df["config"] == config][metric].values[0]
                else:
                    value = np.nan
                row.append(value)
            matrix.append(row)

        # Create heatmap
        ax = axes[idx]
        im = ax.imshow(
            matrix, aspect="auto", cmap="RdBu_r" if "slope" in metric else "viridis"
        )

        # Set ticks
        ax.set_xticks(range(len(epochs_list)))
        ax.set_xticklabels(epochs_list)
        ax.set_yticks(range(len(top_configs)))
        ax.set_yticklabels([c[:20] + "..." if len(c) > 20 else c for c in top_configs])

        # Labels
        ax.set_xlabel("Number of Early Epochs")
        ax.set_title(f"{metric.replace('_', ' ').title()} Across Epoch Cutoffs")

        # Colorbar
        plt.colorbar(im, ax=ax)

    plt.suptitle(
        "Top 15 Configurations: Metric Values vs Early Epoch Cutoff", fontsize=16
    )
    plt.tight_layout()
    plt.savefig(
        output_path / "metrics_heatmap_vs_early_epochs.png",
        dpi=300,
        bbox_inches="tight",
    )
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Sweep early epochs for regression analysis"
    )
    parser.add_argument(
        "--base-path", type=str, default=".", help="Base path for experiments"
    )
    parser.add_argument("--experiment", type=str, required=True, help="Experiment name")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="na_full_t1/early_epochs_sweep",
        help="Output directory",
    )
    parser.add_argument(
        "--min-epochs", type=int, default=3, help="Minimum epochs to use"
    )
    parser.add_argument(
        "--max-epochs", type=int, default=30, help="Maximum epochs to use"
    )
    parser.add_argument("--step", type=int, default=2, help="Step size for epoch sweep")
    args = parser.parse_args()

    # Setup paths
    exp_dir = Path(args.base_path) / args.experiment
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load experiment data
    print(f"Loading experiment data from {exp_dir}...")
    config_results = load_experiment_data(exp_dir)
    print(f"Found {len(config_results)} unique configurations")

    # Define epoch range
    epoch_range = list(range(args.min_epochs, args.max_epochs + 1, args.step))
    print(f"\nSweeping over epochs: {epoch_range}")

    # Perform sweep
    results_by_epoch = sweep_early_epochs(config_results, epoch_range)

    # Create visualizations
    print("\nCreating visualizations...")
    create_correlation_sweep_plots(results_by_epoch, output_dir)
    create_heatmap_plot(results_by_epoch, output_dir)

    print(f"\nAnalysis complete! Results saved to {output_dir}/")
    print("Files created:")
    print(
        "- correlation_vs_early_epochs.png: How correlations change with epoch cutoff"
    )
    print("- best_predictor_vs_early_epochs.png: Which metric is best at each cutoff")
    print(
        "- metrics_heatmap_vs_early_epochs.png: Heatmap of top configs across cutoffs"
    )
    print("- early_epochs_sweep_summary.csv: Detailed correlation data")


if __name__ == "__main__":
    main()
