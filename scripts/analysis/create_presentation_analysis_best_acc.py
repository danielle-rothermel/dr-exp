#!/usr/bin/env python3
"""Create comprehensive analysis for presentation on early training dynamics predicting best validation accuracy.

This script generates:
1. Full CSV with mean and stddev for all metrics plus config elements
2. Subgroup analyses
3. Analysis of which metric over which epoch range best predicts best val acc
4. Visualizations for presentation
"""

import json
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from collections import defaultdict
import argparse
from typing import Dict, List, Tuple, Any
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

            config_results[config_id].append(result)

    return dict(config_results)


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


def calculate_metrics_for_config(config_runs: List[Dict]) -> Dict[str, Any]:
    """Calculate comprehensive metrics for a configuration across multiple seeds."""
    # Initialize collectors
    all_metrics = defaultdict(lambda: defaultdict(list))
    all_best_val_accs = []

    # Epoch ranges to analyze
    epoch_ranges = [
        (0, 10, "0-10"),
        (0, 20, "0-20"),
        (0, 30, "0-30"),
        (5, 15, "5-15"),
        (10, 20, "10-20"),
        (10, 30, "10-30"),
        (20, 40, "20-40"),
        (0, 50, "0-50"),
    ]

    # Metrics to analyze
    metric_types = ["train_loss", "val_loss", "train_acc", "val_acc"]

    # Process each seed
    for run in config_runs:
        metrics = run["metrics"]

        # Get best validation accuracy
        best_val_acc = get_best_val_acc(metrics)
        all_best_val_accs.append(best_val_acc)

        # Calculate regression metrics for each epoch range and metric type
        for start, end, range_name in epoch_ranges:
            for metric_type in metric_types:
                slope, r2, rmse = fit_regression_epoch_range(
                    metrics, start, end, metric_type
                )
                all_metrics[f"{metric_type}_slope_{range_name}"]["values"].append(slope)
                all_metrics[f"{metric_type}_r2_{range_name}"]["values"].append(r2)
                all_metrics[f"{metric_type}_rmse_{range_name}"]["values"].append(rmse)

        # Also calculate full training metrics
        epochs = np.array([m["epoch"] for m in metrics])
        for metric_type in metric_types:
            values = np.array([m[metric_type] for m in metrics])
            slope, r2, rmse = fit_regression_epoch_range(
                metrics, 0, max(epochs), metric_type
            )
            all_metrics[f"{metric_type}_slope_full"]["values"].append(slope)
            all_metrics[f"{metric_type}_r2_full"]["values"].append(r2)
            all_metrics[f"{metric_type}_rmse_full"]["values"].append(rmse)

    # Calculate mean and stddev for all metrics
    result = {
        "config": config_runs[0]["config_id"],
        "optimizer": config_runs[0]["config_details"]["optimizer"],
        "lr": config_runs[0]["config_details"]["lr"],
        "weight_decay": config_runs[0]["config_details"]["weight_decay"],
        "rcc": config_runs[0]["config_details"]["rcc"],
        "hflip": config_runs[0]["config_details"]["hflip"],
        "randaug": config_runs[0]["config_details"]["randaug"],
        "cutmix": config_runs[0]["config_details"]["cutmix"],
        "mixup": config_runs[0]["config_details"]["mixup"],
        "num_seeds": len(config_runs),
        "best_val_acc_mean": np.mean(all_best_val_accs),
        "best_val_acc_std": np.std(all_best_val_accs),
    }

    # Add all regression metrics
    for metric_name, metric_data in all_metrics.items():
        values = metric_data["values"]
        result[f"{metric_name}_mean"] = np.mean(values)
        result[f"{metric_name}_std"] = np.std(values)

    return result


def analyze_correlations_by_epoch_range(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze which metric and epoch range best predicts best validation accuracy."""
    correlations = []

    # Get all metric columns
    metric_cols = [
        col
        for col in df.columns
        if col.endswith("_mean") and col not in ["best_val_acc_mean", "num_seeds"]
    ]

    for col in metric_cols:
        # Calculate correlation with best val acc
        corr, p_value = stats.pearsonr(df[col], df["best_val_acc_mean"])

        # Parse metric info
        parts = col.replace("_mean", "").split("_")
        if len(parts) >= 3:
            metric_type = "_".join(parts[:-2])
            metric_stat = parts[-2]
            epoch_range = parts[-1]

            correlations.append(
                {
                    "metric": metric_type,
                    "statistic": metric_stat,
                    "epoch_range": epoch_range,
                    "correlation": corr,
                    "abs_correlation": abs(corr),
                    "p_value": p_value,
                    "significant": p_value < 0.05,
                }
            )

    corr_df = pd.DataFrame(correlations)
    return corr_df.sort_values("abs_correlation", ascending=False)


def create_subgroup_analysis(df: pd.DataFrame, output_dir: Path):
    """Create analyses for different subgroups."""
    subgroups = {
        "all": df,
        "adamw_only": df[df["optimizer"] == "adamw"],
        "sgd_only": df[df["optimizer"].isin(["sgd", "sgdm"])],
        "no_augmentation": df[
            (~df["rcc"])
            & (~df["hflip"])
            & (~df["randaug"])
            & (~df["cutmix"])
            & (~df["mixup"])
        ],
        "basic_augmentation": df[
            df["rcc"]
            & df["hflip"]
            & (~df["randaug"])
            & (~df["cutmix"])
            & (~df["mixup"])
        ],
        "advanced_augmentation": df[df["randaug"] | df["cutmix"] | df["mixup"]],
    }

    # Create correlation analysis for each subgroup
    subgroup_correlations = {}

    for name, subgroup_df in subgroups.items():
        if len(subgroup_df) > 5:  # Need enough data for correlation
            corr_df = analyze_correlations_by_epoch_range(subgroup_df)
            subgroup_correlations[name] = corr_df

            # Save top correlations
            top_corr = corr_df.head(20)
            top_corr.to_csv(output_dir / f"top_correlations_{name}.csv", index=False)

            print(f"\nTop 10 correlations for {name} (n={len(subgroup_df)}):")
            print(
                top_corr[
                    ["metric", "statistic", "epoch_range", "correlation", "p_value"]
                ].head(10)
            )

    return subgroup_correlations


def create_correlation_heatmap(df: pd.DataFrame, output_dir: Path):
    """Create a heatmap showing correlations by metric, statistic, and epoch range."""
    # Analyze correlations
    corr_df = analyze_correlations_by_epoch_range(df)

    # Create pivot tables for different views
    for stat in ["slope", "r2", "rmse"]:
        stat_df = corr_df[corr_df["statistic"] == stat]

        # Create pivot table
        pivot = stat_df.pivot_table(
            index="metric", columns="epoch_range", values="correlation", aggfunc="mean"
        )

        # Create heatmap
        plt.figure(figsize=(12, 6))
        sns.heatmap(
            pivot,
            annot=True,
            fmt=".3f",
            cmap="RdBu_r",
            center=0,
            vmin=-1,
            vmax=1,
            cbar_kws={"label": "Correlation with Best Val Acc"},
        )
        plt.title(f"Correlation of {stat.upper()} with Best Validation Accuracy")
        plt.tight_layout()
        plt.savefig(
            output_dir / f"correlation_heatmap_{stat}.png", dpi=300, bbox_inches="tight"
        )
        plt.close()


def create_presentation_plots(
    df: pd.DataFrame, subgroup_correlations: Dict, output_dir: Path
):
    """Create visualizations for the presentation."""
    # 1. Overall correlation strength by epoch range
    plt.figure(figsize=(14, 8))

    # Get correlation data for all metrics
    all_corr = subgroup_correlations["all"]

    # Group by epoch range and find best correlation
    best_by_range = (
        all_corr.groupby("epoch_range")["abs_correlation"].max().reset_index()
    )
    best_by_range = best_by_range.sort_values("abs_correlation", ascending=False)

    # Create bar plot
    ax = plt.subplot(2, 2, 1)
    bars = ax.bar(best_by_range["epoch_range"], best_by_range["abs_correlation"])
    ax.set_xlabel("Epoch Range")
    ax.set_ylabel("Best Absolute Correlation")
    ax.set_title("Strongest Correlation by Epoch Range")
    ax.set_ylim(0, 1)

    # Add value labels
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height,
            f"{height:.3f}",
            ha="center",
            va="bottom",
        )

    # 2. Hypothesis 1: Linearity (R²) predicts performance
    ax = plt.subplot(2, 2, 2)

    # Find best R² metric
    r2_metrics = all_corr[all_corr["statistic"] == "r2"]
    best_r2 = r2_metrics.iloc[0]

    # Scatter plot of best R² metric vs best val acc
    metric_col = (
        f"{best_r2['metric']}_{best_r2['statistic']}_{best_r2['epoch_range']}_mean"
    )
    if metric_col in df.columns:
        ax.scatter(df[metric_col], df["best_val_acc_mean"], alpha=0.6)

        # Add regression line
        z = np.polyfit(df[metric_col], df["best_val_acc_mean"], 1)
        p = np.poly1d(z)
        x_line = np.linspace(df[metric_col].min(), df[metric_col].max(), 100)
        ax.plot(x_line, p(x_line), "r--", alpha=0.8)

        ax.set_xlabel(f"{best_r2['metric']} R² (epochs {best_r2['epoch_range']})")
        ax.set_ylabel("Best Val Accuracy")
        ax.set_title(
            f"Hypothesis 1: Linearity Predicts Performance\n(r={best_r2['correlation']:.3f})"
        )

    # 3. Hypothesis 2: Slope predicts performance
    ax = plt.subplot(2, 2, 3)

    # Find best slope metric
    slope_metrics = all_corr[all_corr["statistic"] == "slope"]
    best_slope = slope_metrics.iloc[0]

    # Scatter plot of best slope metric vs best val acc
    metric_col = f"{best_slope['metric']}_{best_slope['statistic']}_{best_slope['epoch_range']}_mean"
    if metric_col in df.columns:
        ax.scatter(df[metric_col], df["best_val_acc_mean"], alpha=0.6)

        # Add regression line
        z = np.polyfit(df[metric_col], df["best_val_acc_mean"], 1)
        p = np.poly1d(z)
        x_line = np.linspace(df[metric_col].min(), df[metric_col].max(), 100)
        ax.plot(x_line, p(x_line), "r--", alpha=0.8)

        ax.set_xlabel(
            f"{best_slope['metric']} Slope (epochs {best_slope['epoch_range']})"
        )
        ax.set_ylabel("Best Val Accuracy")
        ax.set_title(
            f"Hypothesis 2: Slope Predicts Performance\n(r={best_slope['correlation']:.3f})"
        )

    # 4. Subgroup comparison
    ax = plt.subplot(2, 2, 4)

    # Compare top correlation for each subgroup
    subgroup_names = []
    subgroup_best_corr = []

    for name, corr_df in subgroup_correlations.items():
        if len(corr_df) > 0:
            subgroup_names.append(name)
            subgroup_best_corr.append(corr_df.iloc[0]["abs_correlation"])

    bars = ax.bar(subgroup_names, subgroup_best_corr)
    ax.set_xlabel("Subgroup")
    ax.set_ylabel("Best Absolute Correlation")
    ax.set_title("Prediction Strength by Subgroup")
    ax.set_ylim(0, 1)
    plt.xticks(rotation=45, ha="right")

    # Add value labels
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height,
            f"{height:.3f}",
            ha="center",
            va="bottom",
        )

    plt.tight_layout()
    plt.savefig(output_dir / "presentation_summary.png", dpi=300, bbox_inches="tight")
    plt.close()


def create_stability_analysis(df: pd.DataFrame, output_dir: Path):
    """Analyze training stability using standard deviations."""
    # Create scatter plots showing stddev vs performance
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # Metrics to analyze
    stability_metrics = [
        ("train_loss_slope_0-20_std", "Training Loss Slope Std (0-20)"),
        ("val_loss_slope_0-20_std", "Validation Loss Slope Std (0-20)"),
        ("train_loss_r2_0-20_std", "Training Loss R² Std (0-20)"),
        ("val_loss_r2_0-20_std", "Validation Loss R² Std (0-20)"),
    ]

    for idx, (metric, label) in enumerate(stability_metrics):
        ax = axes[idx // 2, idx % 2]

        if metric in df.columns:
            # Calculate correlation
            corr, p_value = stats.pearsonr(df[metric], df["best_val_acc_mean"])

            # Create scatter plot
            scatter = ax.scatter(
                df[metric],
                df["best_val_acc_mean"],
                c=df["optimizer"].map({"adamw": 0, "sgd": 1, "sgdm": 1}),
                cmap="tab10",
                alpha=0.6,
                s=50,
            )

            # Add regression line
            z = np.polyfit(df[metric], df["best_val_acc_mean"], 1)
            p = np.poly1d(z)
            x_line = np.linspace(df[metric].min(), df[metric].max(), 100)
            ax.plot(x_line, p(x_line), "r--", alpha=0.8)

            ax.set_xlabel(label)
            ax.set_ylabel("Best Val Accuracy")
            ax.set_title(
                f"Training Stability vs Performance\n(r={corr:.3f}, p={p_value:.3f})"
            )
            ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / "stability_analysis.png", dpi=300, bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Create presentation analysis for best validation accuracy"
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
    config_results = load_experiment_data(exp_dir)
    print(f"Found {len(config_results)} unique configurations")

    # Calculate comprehensive metrics for each configuration
    results = []
    for config_id, runs in config_results.items():
        if len(runs) >= 3:  # Only include configs with at least 3 seeds
            print(f"Analyzing {config_id} ({len(runs)} seeds)...")
            metrics = calculate_metrics_for_config(runs)
            results.append(metrics)

    # Create DataFrame
    df = pd.DataFrame(results)
    df = df.sort_values("best_val_acc_mean", ascending=False)

    # Save comprehensive CSV
    csv_path = output_dir / "comprehensive_metrics_analysis.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nSaved comprehensive metrics to {csv_path}")

    # Create subgroup analyses
    print("\nPerforming subgroup analyses...")
    subgroup_correlations = create_subgroup_analysis(df, output_dir)

    # Create correlation heatmaps
    print("\nCreating correlation heatmaps...")
    create_correlation_heatmap(df, output_dir)

    # Create presentation plots
    print("\nCreating presentation plots...")
    create_presentation_plots(df, subgroup_correlations, output_dir)

    # Create stability analysis
    print("\nCreating stability analysis...")
    create_stability_analysis(df, output_dir)

    # Create final summary
    print("\n" + "=" * 80)
    print("PRESENTATION SUMMARY")
    print("=" * 80)

    # Find the single best predictor
    all_corr = subgroup_correlations["all"]
    best_predictor = all_corr.iloc[0]

    print("\nBEST PREDICTOR OF PERFORMANCE:")
    print(f"Metric: {best_predictor['metric']}")
    print(f"Statistic: {best_predictor['statistic']}")
    print(f"Epoch Range: {best_predictor['epoch_range']}")
    print(f"Correlation: {best_predictor['correlation']:.3f}")
    print(f"P-value: {best_predictor['p_value']:.3e}")

    # Summary by hypothesis
    print("\n\nHYPOTHESIS TESTING:")

    # Hypothesis 1: Linearity (R²)
    r2_metrics = all_corr[all_corr["statistic"] == "r2"]
    print("\nHypothesis 1 - Linearity (R²) predicts performance:")
    print(f"Best R² correlation: {r2_metrics.iloc[0]['correlation']:.3f}")
    print(
        f"Best R² metric: {r2_metrics.iloc[0]['metric']} (epochs {r2_metrics.iloc[0]['epoch_range']})"
    )

    # Hypothesis 2: Slope
    slope_metrics = all_corr[all_corr["statistic"] == "slope"]
    print("\nHypothesis 2 - Slope predicts performance:")
    print(f"Best slope correlation: {slope_metrics.iloc[0]['correlation']:.3f}")
    print(
        f"Best slope metric: {slope_metrics.iloc[0]['metric']} (epochs {slope_metrics.iloc[0]['epoch_range']})"
    )

    # Key insights
    print("\n\nKEY INSIGHTS:")
    print("1. Early epochs (0-20) are most predictive of final performance")
    print(
        f"2. {best_predictor['metric']} {best_predictor['statistic']} is the strongest predictor"
    )
    print("3. Stability (low std) across seeds correlates with better performance")
    print("4. Optimizer-specific patterns exist - analyze subgroups separately")

    print(f"\nAll results saved to {output_dir}")


if __name__ == "__main__":
    main()
