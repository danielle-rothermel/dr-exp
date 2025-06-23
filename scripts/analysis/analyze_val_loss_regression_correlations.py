#!/usr/bin/env python3
"""Analyze correlations between validation loss regression characteristics and final validation accuracy."""

import json
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict
from scipy import stats
import pandas as pd


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


def collect_experiment_data(base_path: Path, experiment: str) -> Dict[str, List]:
    """Collect all experiment data including final validation accuracy."""
    exp_dir = base_path / experiment
    storage_dir = exp_dir / "storage"

    config_results = defaultdict(list)

    for run_dir in storage_dir.glob("run_*"):
        if not run_dir.is_dir():
            continue

        job_id = run_dir.name.replace("run_", "")
        job_file = exp_dir / "jobs" / f"{job_id}.json"

        if not job_file.exists():
            continue

        with open(job_file, "r") as f:
            job = json.load(f)

        if job["status"] != "completed":
            continue

        config_name = job["config"].get(
            "run_name", job["config"].get("config_name", "unknown")
        )

        if not should_include_config(config_name):
            continue

        metrics_file = run_dir / "metrics.jsonl"
        if not metrics_file.exists():
            continue

        metrics = load_metrics(metrics_file)
        if not metrics:
            continue

        display_name = renumber_step_name(config_name)

        # Get final validation accuracy and loss
        final_val_acc = metrics[-1].get("val_acc", np.nan)
        final_val_loss = metrics[-1].get("val_loss", np.nan)

        config_results[display_name].append(
            {
                "metrics": metrics,
                "final_val_acc": final_val_acc,
                "final_val_loss": final_val_loss,
            }
        )

    return config_results


def fit_regression_with_rmse(
    epochs: np.ndarray, losses: np.ndarray, max_epoch: int = 25
) -> Tuple[float, float, float, float]:
    """Fit linear regression and calculate RMSE."""
    # Filter to first max_epoch epochs
    mask = epochs < max_epoch
    epochs_subset = epochs[mask] + 1  # Add 1 to avoid log(0)
    losses_subset = losses[mask]

    # Remove any NaN values
    valid_mask = ~np.isnan(losses_subset)
    epochs_subset = epochs_subset[valid_mask]
    losses_subset = losses_subset[valid_mask]

    if len(epochs_subset) < 2:
        return np.nan, np.nan, np.nan, np.nan

    # Fit linear regression on log(epoch) vs loss
    log_epochs = np.log(epochs_subset)
    slope, intercept, r_value, p_value, std_err = stats.linregress(
        log_epochs, losses_subset
    )

    # Calculate predictions and RMSE
    predictions = slope * log_epochs + intercept
    rmse = np.sqrt(np.mean((predictions - losses_subset) ** 2))

    return slope, intercept, r_value, rmse


def analyze_correlations(config_results: Dict[str, List], output_dir: Path):
    """Analyze correlations between validation loss regression characteristics and validation accuracy."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect data for all configs
    config_names = []
    slopes = []
    r_squared_values = []
    rmse_values = []
    final_val_accs = []
    final_val_losses = []

    for config_name, results in config_results.items():
        # Calculate mean metrics across seeds
        all_metrics = [r["metrics"] for r in results]
        all_final_val_accs = [r["final_val_acc"] for r in results]
        all_final_val_losses = [r["final_val_loss"] for r in results]

        # Average final validation accuracy and loss
        mean_final_val_acc = np.mean(all_final_val_accs)
        mean_final_val_loss = np.mean(all_final_val_losses)

        # Get average validation loss curve
        max_len = max(len(metrics) for metrics in all_metrics)
        epochs = np.arange(max_len)

        all_val_losses = []
        for metrics in all_metrics:
            val_losses = [m.get("val_loss", np.nan) for m in metrics]
            if len(val_losses) < max_len:
                val_losses.extend([val_losses[-1]] * (max_len - len(val_losses)))
            all_val_losses.append(val_losses)

        mean_val_loss = np.mean(all_val_losses, axis=0)

        # Fit regression on validation loss
        slope, intercept, r_value, rmse = fit_regression_with_rmse(
            epochs, mean_val_loss, max_epoch=25
        )

        if not np.isnan(slope):
            config_names.append(config_name)
            slopes.append(slope)
            r_squared_values.append(r_value**2)
            rmse_values.append(rmse)
            final_val_accs.append(mean_final_val_acc)
            final_val_losses.append(mean_final_val_loss)

    # Convert to numpy arrays
    slopes = np.array(slopes)
    r_squared_values = np.array(r_squared_values)
    rmse_values = np.array(rmse_values)
    final_val_accs = np.array(final_val_accs)
    final_val_losses = np.array(final_val_losses)

    # Create figure with subplots
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 12))

    # 1. Validation Accuracy vs Val Loss Slope
    ax1.scatter(slopes, final_val_accs, s=100, alpha=0.7, c="blue", edgecolors="black")

    # Fit linear regression
    slope_corr, intercept_corr, r_value_corr, p_value_corr, _ = stats.linregress(
        slopes, final_val_accs
    )
    line_x = np.linspace(slopes.min(), slopes.max(), 100)
    line_y = slope_corr * line_x + intercept_corr
    ax1.plot(line_x, line_y, "r--", linewidth=2, alpha=0.8)

    # Calculate correlations
    pearson_r, pearson_p = stats.pearsonr(slopes, final_val_accs)
    spearman_r, spearman_p = stats.spearmanr(slopes, final_val_accs)

    ax1.set_xlabel(
        "Val Loss Regression Slope (more negative = faster improvement)", fontsize=12
    )
    ax1.set_ylabel("Final Validation Accuracy", fontsize=12)
    ax1.set_title("Validation Accuracy vs Validation Loss Slope", fontsize=14)
    ax1.grid(True, alpha=0.3)

    # Add correlation text
    text1 = f"Pearson r = {pearson_r:.3f} (p = {pearson_p:.3f})\n"
    text1 += f"Spearman ρ = {spearman_r:.3f} (p = {spearman_p:.3f})"
    ax1.text(
        0.05,
        0.95,
        text1,
        transform=ax1.transAxes,
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8),
        verticalalignment="top",
    )

    # Add config labels
    for i, config in enumerate(config_names):
        ax1.annotate(
            config.replace("step", ""),
            (slopes[i], final_val_accs[i]),
            fontsize=8,
            ha="center",
            va="bottom",
        )

    # 2. Validation Accuracy vs Val Loss RMSE
    ax2.scatter(
        rmse_values, final_val_accs, s=100, alpha=0.7, c="green", edgecolors="black"
    )

    # Fit linear regression
    rmse_corr, intercept_rmse, r_value_rmse, p_value_rmse, _ = stats.linregress(
        rmse_values, final_val_accs
    )
    line_x = np.linspace(rmse_values.min(), rmse_values.max(), 100)
    line_y = rmse_corr * line_x + intercept_rmse
    ax2.plot(line_x, line_y, "r--", linewidth=2, alpha=0.8)

    # Calculate correlations
    pearson_r2, pearson_p2 = stats.pearsonr(rmse_values, final_val_accs)
    spearman_r2, spearman_p2 = stats.spearmanr(rmse_values, final_val_accs)

    ax2.set_xlabel("Val Loss Regression RMSE (lower = better fit)", fontsize=12)
    ax2.set_ylabel("Final Validation Accuracy", fontsize=12)
    ax2.set_title("Validation Accuracy vs Val Loss Regression Fit Error", fontsize=14)
    ax2.grid(True, alpha=0.3)

    text2 = f"Pearson r = {pearson_r2:.3f} (p = {pearson_p2:.3f})\n"
    text2 += f"Spearman ρ = {spearman_r2:.3f} (p = {spearman_p2:.3f})"
    ax2.text(
        0.05,
        0.95,
        text2,
        transform=ax2.transAxes,
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8),
        verticalalignment="top",
    )

    # 3. Validation Accuracy vs Val Loss R²
    ax3.scatter(
        r_squared_values,
        final_val_accs,
        s=100,
        alpha=0.7,
        c="orange",
        edgecolors="black",
    )

    # Fit linear regression
    r2_corr, intercept_r2, r_value_r2, p_value_r2, _ = stats.linregress(
        r_squared_values, final_val_accs
    )
    line_x = np.linspace(r_squared_values.min(), r_squared_values.max(), 100)
    line_y = r2_corr * line_x + intercept_r2
    ax3.plot(line_x, line_y, "r--", linewidth=2, alpha=0.8)

    # Calculate correlations
    pearson_r3, pearson_p3 = stats.pearsonr(r_squared_values, final_val_accs)
    spearman_r3, spearman_p3 = stats.spearmanr(r_squared_values, final_val_accs)

    ax3.set_xlabel("Val Loss Regression R² (higher = better fit)", fontsize=12)
    ax3.set_ylabel("Final Validation Accuracy", fontsize=12)
    ax3.set_title("Validation Accuracy vs Val Loss Regression R²", fontsize=14)
    ax3.grid(True, alpha=0.3)

    text3 = f"Pearson r = {pearson_r3:.3f} (p = {pearson_p3:.3f})\n"
    text3 += f"Spearman ρ = {spearman_r3:.3f} (p = {spearman_p3:.3f})"
    ax3.text(
        0.05,
        0.95,
        text3,
        transform=ax3.transAxes,
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8),
        verticalalignment="top",
    )

    # 4. Final Val Loss vs Final Val Accuracy (sanity check)
    ax4.scatter(
        final_val_losses,
        final_val_accs,
        s=100,
        alpha=0.7,
        c="purple",
        edgecolors="black",
    )

    pearson_r4, pearson_p4 = stats.pearsonr(final_val_losses, final_val_accs)

    ax4.set_xlabel("Final Validation Loss", fontsize=12)
    ax4.set_ylabel("Final Validation Accuracy", fontsize=12)
    ax4.set_title("Final Loss vs Accuracy Relationship", fontsize=14)
    ax4.grid(True, alpha=0.3)

    text4 = f"Pearson r = {pearson_r4:.3f} (p = {pearson_p4:.3f})"
    ax4.text(
        0.05,
        0.95,
        text4,
        transform=ax4.transAxes,
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8),
        verticalalignment="top",
    )

    plt.suptitle(
        "Validation Loss Regression Characteristics vs Final Performance", fontsize=16
    )
    plt.tight_layout()
    plt.savefig(
        output_dir / "val_loss_regression_correlation_analysis.png",
        dpi=150,
        bbox_inches="tight",
    )
    plt.close()

    # Create validation loss regression plots
    fig2, axes = plt.subplots(1, 3, figsize=(18, 6))

    # Groups
    sorted_configs = sorted(config_results.keys())
    groups = [
        ("Group 1: Baseline & Core Changes", sorted_configs[0:5]),
        ("Group 2: Scheduler & Architecture", sorted_configs[5:10]),
        ("Group 3: Activation & Aug Details", sorted_configs[10:15]),
    ]

    colors = plt.cm.tab20(np.linspace(0, 1, 15))

    for group_idx, (group_name, group_configs) in enumerate(groups):
        ax = axes[group_idx]

        for i, config in enumerate(group_configs):
            # Get average validation loss curve
            results = config_results[config]
            all_metrics = [r["metrics"] for r in results]

            max_len = max(len(metrics) for metrics in all_metrics)
            epochs = np.arange(max_len)

            all_val_losses = []
            for metrics in all_metrics:
                val_losses = [m.get("val_loss", np.nan) for m in metrics]
                if len(val_losses) < max_len:
                    val_losses.extend([val_losses[-1]] * (max_len - len(val_losses)))
                all_val_losses.append(val_losses)

            mean_val_loss = np.mean(all_val_losses, axis=0)

            color_idx = sorted_configs.index(config)

            # Plot validation loss on log scale
            ax.semilogx(
                epochs + 1,
                mean_val_loss,
                color=colors[color_idx],
                linewidth=2,
                alpha=0.7,
                label=config.replace("step", ""),
            )

            # Fit and plot regression
            slope, intercept, r_value, rmse = fit_regression_with_rmse(
                epochs, mean_val_loss, max_epoch=25
            )

            if not np.isnan(slope):
                # Plot regression line on log scale
                epochs_line = np.logspace(0, np.log10(25), 100)
                regression_line = slope * np.log(epochs_line) + intercept
                ax.plot(
                    epochs_line,
                    regression_line,
                    color=colors[color_idx],
                    linestyle="--",
                    linewidth=1.5,
                    alpha=0.8,
                )

        ax.set_xlabel("Epoch (log scale)", fontsize=12)
        ax.set_ylabel("Validation Loss", fontsize=12)
        ax.set_title(f"{group_name}", fontsize=13)
        ax.grid(True, alpha=0.3, which="both")
        ax.set_xlim(1, 50)
        ax.axvline(x=25, color="gray", linestyle=":", alpha=0.5)
        ax.legend(fontsize=9, loc="upper right")

    plt.suptitle(
        "Validation Loss with Log-Linear Regression (First 25 Epochs)", fontsize=14
    )
    plt.tight_layout()
    plt.savefig(
        output_dir / "grouped_val_loss_regression.png", dpi=150, bbox_inches="tight"
    )
    plt.close()

    # Create summary table
    summary_data = []
    for i, config in enumerate(config_names):
        summary_data.append(
            {
                "Config": config,
                "Val Loss Slope": slopes[i],
                "Val Loss R²": r_squared_values[i],
                "Val Loss RMSE": rmse_values[i],
                "Final Val Loss": final_val_losses[i],
                "Final Val Acc": final_val_accs[i],
            }
        )

    df = pd.DataFrame(summary_data)
    df = df.sort_values("Final Val Acc", ascending=False)

    # Save as CSV
    df.to_csv(
        output_dir / "val_loss_regression_analysis_summary.csv",
        index=False,
        float_format="%.4f",
    )

    # Print summary
    print("\nValidation Loss Correlation Analysis Summary:")
    print("=" * 70)
    print(f"{'Metric Pair':<45} {'Pearson r':>10} {'p-value':>10}")
    print("-" * 70)
    print(
        f"{'Val Loss Slope vs Final Val Acc':<45} {pearson_r:>10.3f} {pearson_p:>10.3f}"
    )
    print(
        f"{'Val Loss RMSE vs Final Val Acc':<45} {pearson_r2:>10.3f} {pearson_p2:>10.3f}"
    )
    print(
        f"{'Val Loss R² vs Final Val Acc':<45} {pearson_r3:>10.3f} {pearson_p3:>10.3f}"
    )
    print(
        f"{'Final Val Loss vs Final Val Acc':<45} {pearson_r4:>10.3f} {pearson_p4:>10.3f}"
    )
    print("=" * 70)

    print("\nTop 5 configs by validation accuracy:")
    print(df.head().to_string(index=False))

    return df


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze validation loss regression correlations"
    )
    parser.add_argument("--base-path", type=Path, default=Path("."))
    parser.add_argument("--experiment", type=str, default="cluster_t0")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("./val_loss_correlation_analysis")
    )

    args = parser.parse_args()

    print(f"Loading experiments from {args.base_path / args.experiment}")
    config_results = collect_experiment_data(args.base_path, args.experiment)

    print(f"Found {len(config_results)} configurations")
    df = analyze_correlations(config_results, args.output_dir)


if __name__ == "__main__":
    main()
