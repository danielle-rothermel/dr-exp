#!/usr/bin/env python3
"""Analyze which epoch ranges are most predictive of final performance."""

import json
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from collections import defaultdict
import argparse
from typing import Dict, List, Tuple
import warnings

warnings.filterwarnings("ignore")


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
        if lr and lr != 0.001:
            base_name += f"_lr{lr}"
        if wd and wd != 0.01:
            base_name += f"_wd{wd}"
    elif (
        "sgd" in base_name
        or base_name.startswith("step01")
        or base_name.startswith("controlled")
    ):
        # SGD configs
        if lr and lr != 0.1:
            base_name += f"_lr{lr}"
        if wd and wd != 0.0005:
            base_name += f"_wd{wd}"

    return base_name


def renumber_step_name(step_name: str) -> str:
    """Renumber step names to account for removed steps."""
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


def load_experiment_data(exp_dir: Path) -> Tuple[List[Dict], Dict[str, Dict]]:
    """Load all experiment data and return both raw data and grouped by config."""
    jobs_dir = exp_dir / "jobs"
    storage_dir = exp_dir / "storage"

    all_runs = []
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

        if metrics:
            # Extract config details
            config_details = {
                "optimizer": job["config"]["optim"]["name"],
                "lr": job["config"]["optim"]["lr"],
                "weight_decay": job["config"]["optim"]["weight_decay"],
                "rcc": job["config"]["train_transforms"].get("rcc", False),
                "hflip": job["config"]["train_transforms"].get("hflip", False),
                "randaug": job["config"]["train_transforms"].get("randaug", False),
                "cutmix": job["config"]["train_transforms"].get("cutmix", False),
                "mixup": job["config"]["train_transforms"].get("mixup", False),
            }

            result = {
                "job_id": job["id"],
                "config_id": config_id,
                "seed": job["config"].get("seed", -1),
                "metrics": metrics,
                "final_metrics": job.get("final_metrics", {}),
                "tags": job.get("tags", []),
                "config_details": config_details,
            }

            all_runs.append(result)
            config_results[config_id].append(result)

    return all_runs, dict(config_results)


def get_best_val_acc(metrics: List[Dict]) -> float:
    """Find the best (maximum) validation accuracy across all epochs."""
    val_accs = [m.get("val_acc", 0) for m in metrics]
    return max(val_accs) if val_accs else 0


def fit_regression_epoch_range(
    metrics: List[Dict],
    start_epoch: int,
    end_epoch: int,
    metric_type: str = "train_loss",
) -> Tuple[float, float, float]:
    """Fit linear regression to log(epoch) vs metric for a specific epoch range."""
    # Filter metrics to epoch range
    filtered_metrics = [m for m in metrics if start_epoch <= m["epoch"] <= end_epoch]

    if len(filtered_metrics) < 2:
        return 0, 0, float("inf")

    epochs = np.array([m["epoch"] for m in filtered_metrics])
    values = np.array([m[metric_type] for m in filtered_metrics])

    # Use log(epoch + 1) to handle epoch 0
    log_epochs = np.log(epochs + 1)

    # Fit linear regression
    slope, intercept = np.polyfit(log_epochs, values, 1)

    # Calculate R² and RMSE
    predictions = slope * log_epochs + intercept
    ss_res = np.sum((values - predictions) ** 2)
    ss_tot = np.sum((values - np.mean(values)) ** 2)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    rmse = np.sqrt(np.mean((values - predictions) ** 2))

    return slope, r_squared, rmse


def analyze_epoch_ranges(all_runs: List[Dict], output_dir: Path):
    """Analyze correlations for different epoch ranges and window sizes."""

    # Define epoch ranges with different window sizes
    window_sizes = [5, 10, 15, 20, 30]
    start_epochs = [0, 5, 10, 15, 20]

    # Metrics to analyze
    metric_types = ["train_loss", "val_loss", "train_acc", "val_acc"]
    statistics = ["slope", "r2", "rmse"]

    # Collect results
    results = []

    for window_size in window_sizes:
        for start_epoch in start_epochs:
            end_epoch = start_epoch + window_size

            # Skip if end epoch is too large
            if end_epoch > 50:
                continue

            range_name = f"{start_epoch}-{end_epoch}"

            # Calculate metrics for each run
            run_metrics = []
            best_val_accs = []

            for run in all_runs:
                metrics = run["metrics"]

                # Check if we have enough epochs
                max_epoch = max([m["epoch"] for m in metrics])
                if max_epoch < end_epoch:
                    continue

                # Get best validation accuracy
                best_val_acc = get_best_val_acc(metrics)
                best_val_accs.append(best_val_acc)

                # Calculate regression metrics
                run_result = {"best_val_acc": best_val_acc}

                for metric_type in metric_types:
                    slope, r2, rmse = fit_regression_epoch_range(
                        metrics, start_epoch, end_epoch, metric_type
                    )
                    run_result[f"{metric_type}_slope"] = slope
                    run_result[f"{metric_type}_r2"] = r2
                    run_result[f"{metric_type}_rmse"] = rmse

                run_metrics.append(run_result)

            # Calculate correlations if we have enough data
            if len(run_metrics) >= 10:
                df = pd.DataFrame(run_metrics)

                for metric_type in metric_types:
                    for stat in statistics:
                        col_name = f"{metric_type}_{stat}"
                        if col_name in df.columns:
                            corr, p_value = stats.pearsonr(
                                df[col_name], df["best_val_acc"]
                            )

                            results.append(
                                {
                                    "window_size": window_size,
                                    "start_epoch": start_epoch,
                                    "end_epoch": end_epoch,
                                    "range_name": range_name,
                                    "metric": metric_type,
                                    "statistic": stat,
                                    "correlation": corr,
                                    "abs_correlation": abs(corr),
                                    "p_value": p_value,
                                    "n_samples": len(run_metrics),
                                }
                            )

    # Create DataFrame and save
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("abs_correlation", ascending=False)
    results_df.to_csv(output_dir / "epoch_range_correlations.csv", index=False)

    # Create visualizations
    create_epoch_range_plots(results_df, output_dir)

    return results_df


def create_epoch_range_plots(results_df: pd.DataFrame, output_dir: Path):
    """Create visualizations for epoch range analysis."""

    # 1. Heatmap of correlations by window size and start epoch
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # Separate by metric type
    metric_types = ["train_loss", "val_loss", "train_acc", "val_acc"]

    for idx, metric in enumerate(metric_types):
        ax = axes[idx // 2, idx % 2]

        # Filter for this metric and best statistic
        metric_df = results_df[results_df["metric"] == metric]

        # Find best statistic for this metric
        best_stat = metric_df.groupby("statistic")["abs_correlation"].max().idxmax()
        stat_df = metric_df[metric_df["statistic"] == best_stat]

        # Create pivot table
        pivot = stat_df.pivot_table(
            index="start_epoch",
            columns="window_size",
            values="correlation",
            aggfunc="mean",
        )

        # Create heatmap
        sns.heatmap(
            pivot,
            annot=True,
            fmt=".3f",
            cmap="RdBu_r",
            center=0,
            vmin=-1,
            vmax=1,
            ax=ax,
            cbar_kws={"label": "Correlation"},
        )
        ax.set_title(f"{metric} ({best_stat}) - Correlation with Best Val Acc")
        ax.set_xlabel("Window Size (epochs)")
        ax.set_ylabel("Start Epoch")

    plt.tight_layout()
    plt.savefig(output_dir / "epoch_range_heatmaps.png", dpi=300, bbox_inches="tight")
    plt.close()

    # 2. Line plot showing correlation strength by epoch range
    plt.figure(figsize=(14, 8))

    # Get top correlations for each window size
    top_by_window = (
        results_df.groupby("window_size")
        .apply(lambda x: x.nlargest(5, "abs_correlation"))
        .reset_index(drop=True)
    )

    # Create line plot
    for window in sorted(results_df["window_size"].unique()):
        window_df = top_by_window[top_by_window["window_size"] == window]
        window_df = window_df.sort_values("start_epoch")

        plt.plot(
            window_df["start_epoch"],
            window_df["abs_correlation"],
            marker="o",
            label=f"Window: {window} epochs",
            linewidth=2,
        )

    plt.xlabel("Start Epoch")
    plt.ylabel("Absolute Correlation with Best Val Acc")
    plt.title("Prediction Strength by Epoch Range")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(
        output_dir / "correlation_by_epoch_range.png", dpi=300, bbox_inches="tight"
    )
    plt.close()

    # 3. Summary of best predictors
    plt.figure(figsize=(12, 8))

    # Get top 20 overall
    top_20 = results_df.nlargest(20, "abs_correlation")

    # Create bar plot
    y_pos = np.arange(len(top_20))
    labels = [
        f"{row['metric']} {row['statistic']} ({row['range_name']})"
        for _, row in top_20.iterrows()
    ]

    plt.barh(y_pos, top_20["abs_correlation"])
    plt.yticks(y_pos, labels)
    plt.xlabel("Absolute Correlation with Best Val Acc")
    plt.title("Top 20 Predictors Across All Epoch Ranges")
    plt.tight_layout()
    plt.savefig(
        output_dir / "top_predictors_by_range.png", dpi=300, bbox_inches="tight"
    )
    plt.close()


def create_summary_table(results_df: pd.DataFrame, output_dir: Path):
    """Create a summary table of best predictors by category."""

    # Find best predictor for each combination
    summary = []

    # By metric type
    for metric in results_df["metric"].unique():
        metric_df = results_df[results_df["metric"] == metric]
        best = metric_df.loc[metric_df["abs_correlation"].idxmax()]
        summary.append(
            {
                "Category": f"Best {metric}",
                "Metric": best["metric"],
                "Statistic": best["statistic"],
                "Epoch Range": best["range_name"],
                "Correlation": f"{best['correlation']:.3f}",
                "P-value": f"{best['p_value']:.3e}",
            }
        )

    # By window size
    for window in sorted(results_df["window_size"].unique()):
        window_df = results_df[results_df["window_size"] == window]
        best = window_df.loc[window_df["abs_correlation"].idxmax()]
        summary.append(
            {
                "Category": f"Best {window}-epoch window",
                "Metric": best["metric"],
                "Statistic": best["statistic"],
                "Epoch Range": best["range_name"],
                "Correlation": f"{best['correlation']:.3f}",
                "P-value": f"{best['p_value']:.3e}",
            }
        )

    # Overall best
    best = results_df.loc[results_df["abs_correlation"].idxmax()]
    summary.append(
        {
            "Category": "Overall Best",
            "Metric": best["metric"],
            "Statistic": best["statistic"],
            "Epoch Range": best["range_name"],
            "Correlation": f"{best['correlation']:.3f}",
            "P-value": f"{best['p_value']:.3e}",
        }
    )

    # Create DataFrame and save
    summary_df = pd.DataFrame(summary)
    summary_df.to_csv(output_dir / "best_predictors_summary.csv", index=False)

    # Print summary
    print("\nBEST PREDICTORS BY CATEGORY:")
    print("=" * 80)
    print(summary_df.to_string(index=False))

    return summary_df


def main():
    parser = argparse.ArgumentParser(
        description="Analyze epoch ranges for predicting performance"
    )
    parser.add_argument(
        "--base-path", type=str, default=".", help="Base path for experiments"
    )
    parser.add_argument("--experiment", type=str, required=True, help="Experiment name")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="na_full_t1_best_acc/presentation",
        help="Output directory",
    )
    args = parser.parse_args()

    # Setup paths
    exp_dir = Path(args.base_path) / args.experiment
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load experiment data
    print(f"Loading experiment data from {exp_dir}...")
    all_runs, config_results = load_experiment_data(exp_dir)
    print(
        f"Found {len(all_runs)} total runs across {len(config_results)} configurations"
    )

    # Analyze epoch ranges
    print("\nAnalyzing epoch ranges...")
    results_df = analyze_epoch_ranges(all_runs, output_dir)

    # Create summary table
    print("\nCreating summary...")
    summary_df = create_summary_table(results_df, output_dir)

    # Print key insights
    print("\n\nKEY INSIGHTS:")
    print("=" * 80)

    # Best overall predictor
    best = results_df.loc[results_df["abs_correlation"].idxmax()]
    print("\n1. BEST OVERALL PREDICTOR:")
    print(f"   - {best['metric']} {best['statistic']} for epochs {best['range_name']}")
    print(f"   - Correlation: {best['correlation']:.3f} (p={best['p_value']:.3e})")

    # Best window size
    window_summary = results_df.groupby("window_size")["abs_correlation"].agg(
        ["max", "mean"]
    )
    best_window = window_summary["max"].idxmax()
    print(f"\n2. OPTIMAL WINDOW SIZE: {best_window} epochs")
    print(f"   - Max correlation: {window_summary.loc[best_window, 'max']:.3f}")
    print(f"   - Mean correlation: {window_summary.loc[best_window, 'mean']:.3f}")

    # Best start epoch
    start_summary = results_df.groupby("start_epoch")["abs_correlation"].agg(
        ["max", "mean"]
    )
    best_start = start_summary["max"].idxmax()
    print(f"\n3. OPTIMAL START EPOCH: {best_start}")
    print(f"   - Max correlation: {start_summary.loc[best_start, 'max']:.3f}")
    print(f"   - Mean correlation: {start_summary.loc[best_start, 'mean']:.3f}")

    # Early vs late training
    early_df = results_df[results_df["end_epoch"] <= 20]
    late_df = results_df[results_df["start_epoch"] >= 20]

    print("\n4. EARLY vs LATE TRAINING:")
    print(
        f"   - Early training (≤20 epochs) max correlation: {early_df['abs_correlation'].max():.3f}"
    )
    print(
        f"   - Late training (≥20 epochs) max correlation: {late_df['abs_correlation'].max():.3f}"
    )

    print(f"\nAll results saved to {output_dir}")


if __name__ == "__main__":
    main()
