#!/usr/bin/env python3
"""Analyze correlations using only first 10 epochs for regression fitting."""

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
    epochs: np.ndarray, losses: np.ndarray, max_epoch: int = 10
) -> Tuple[float, float, float, float]:
    """Fit linear regression and calculate RMSE using only first 10 epochs."""
    # Filter to first max_epoch epochs
    mask = epochs < max_epoch
    epochs_subset = epochs[mask] + 1
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
    """Analyze correlations for both training and validation loss."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect data for all configs
    config_names = []
    train_slopes = []
    train_r2s = []
    train_rmses = []
    val_slopes = []
    val_r2s = []
    val_rmses = []
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

        # Get average loss curves
        max_len = max(len(metrics) for metrics in all_metrics)
        epochs = np.arange(max_len)

        # Training loss
        all_train_losses = []
        for metrics in all_metrics:
            train_losses = [m.get("train_loss", np.nan) for m in metrics]
            if len(train_losses) < max_len:
                train_losses.extend([train_losses[-1]] * (max_len - len(train_losses)))
            all_train_losses.append(train_losses)
        mean_train_loss = np.mean(all_train_losses, axis=0)

        # Validation loss
        all_val_losses = []
        for metrics in all_metrics:
            val_losses = [m.get("val_loss", np.nan) for m in metrics]
            if len(val_losses) < max_len:
                val_losses.extend([val_losses[-1]] * (max_len - len(val_losses)))
            all_val_losses.append(val_losses)
        mean_val_loss = np.mean(all_val_losses, axis=0)

        # Fit regressions (10 epochs)
        train_slope, _, train_r, train_rmse = fit_regression_with_rmse(
            epochs, mean_train_loss, max_epoch=10
        )
        val_slope, _, val_r, val_rmse = fit_regression_with_rmse(
            epochs, mean_val_loss, max_epoch=10
        )

        if not np.isnan(train_slope) and not np.isnan(val_slope):
            config_names.append(config_name)
            train_slopes.append(train_slope)
            train_r2s.append(train_r**2)
            train_rmses.append(train_rmse)
            val_slopes.append(val_slope)
            val_r2s.append(val_r**2)
            val_rmses.append(val_rmse)
            final_val_accs.append(mean_final_val_acc)
            final_val_losses.append(mean_final_val_loss)

    # Convert to numpy arrays
    train_slopes = np.array(train_slopes)
    train_r2s = np.array(train_r2s)
    train_rmses = np.array(train_rmses)
    val_slopes = np.array(val_slopes)
    val_r2s = np.array(val_r2s)
    val_rmses = np.array(val_rmses)
    final_val_accs = np.array(final_val_accs)

    # Create comprehensive figure
    fig = plt.figure(figsize=(16, 12))

    # Train Loss Slope vs Val Acc
    ax1 = plt.subplot(3, 3, 1)
    ax1.scatter(
        train_slopes, final_val_accs, s=100, alpha=0.7, c="blue", edgecolors="black"
    )
    pearson_r1, pearson_p1 = stats.pearsonr(train_slopes, final_val_accs)
    # Add trend line
    slope1, intercept1, _, _, _ = stats.linregress(train_slopes, final_val_accs)
    line_x1 = np.linspace(train_slopes.min(), train_slopes.max(), 100)
    ax1.plot(line_x1, slope1 * line_x1 + intercept1, "r--", linewidth=2, alpha=0.8)
    ax1.set_xlabel("Train Loss Slope (10 epochs)")
    ax1.set_ylabel("Final Val Accuracy")
    ax1.set_title(f"r = {pearson_r1:.3f} (p = {pearson_p1:.3f})")
    ax1.grid(True, alpha=0.3)

    # Train Loss RMSE vs Val Acc
    ax2 = plt.subplot(3, 3, 2)
    ax2.scatter(
        train_rmses, final_val_accs, s=100, alpha=0.7, c="green", edgecolors="black"
    )
    pearson_r2, pearson_p2 = stats.pearsonr(train_rmses, final_val_accs)
    # Add trend line
    slope2, intercept2, _, _, _ = stats.linregress(train_rmses, final_val_accs)
    line_x2 = np.linspace(train_rmses.min(), train_rmses.max(), 100)
    ax2.plot(line_x2, slope2 * line_x2 + intercept2, "r--", linewidth=2, alpha=0.8)
    ax2.set_xlabel("Train Loss RMSE (10 epochs)")
    ax2.set_ylabel("Final Val Accuracy")
    ax2.set_title(f"r = {pearson_r2:.3f} (p = {pearson_p2:.3f})")
    ax2.grid(True, alpha=0.3)

    # Train Loss R² vs Val Acc
    ax3 = plt.subplot(3, 3, 3)
    ax3.scatter(
        train_r2s, final_val_accs, s=100, alpha=0.7, c="orange", edgecolors="black"
    )
    pearson_r3, pearson_p3 = stats.pearsonr(train_r2s, final_val_accs)
    # Add trend line
    slope3, intercept3, _, _, _ = stats.linregress(train_r2s, final_val_accs)
    line_x3 = np.linspace(train_r2s.min(), train_r2s.max(), 100)
    ax3.plot(line_x3, slope3 * line_x3 + intercept3, "r--", linewidth=2, alpha=0.8)
    ax3.set_xlabel("Train Loss R² (10 epochs)")
    ax3.set_ylabel("Final Val Accuracy")
    ax3.set_title(f"r = {pearson_r3:.3f} (p = {pearson_p3:.3f})")
    ax3.grid(True, alpha=0.3)

    # Val Loss Slope vs Val Acc
    ax4 = plt.subplot(3, 3, 4)
    ax4.scatter(
        val_slopes, final_val_accs, s=100, alpha=0.7, c="red", edgecolors="black"
    )
    pearson_r4, pearson_p4 = stats.pearsonr(val_slopes, final_val_accs)
    # Add trend line
    slope4, intercept4, _, _, _ = stats.linregress(val_slopes, final_val_accs)
    line_x4 = np.linspace(val_slopes.min(), val_slopes.max(), 100)
    ax4.plot(line_x4, slope4 * line_x4 + intercept4, "r--", linewidth=2, alpha=0.8)
    ax4.set_xlabel("Val Loss Slope (10 epochs)")
    ax4.set_ylabel("Final Val Accuracy")
    ax4.set_title(f"r = {pearson_r4:.3f} (p = {pearson_p4:.3f})")
    ax4.grid(True, alpha=0.3)

    # Val Loss RMSE vs Val Acc
    ax5 = plt.subplot(3, 3, 5)
    ax5.scatter(
        val_rmses, final_val_accs, s=100, alpha=0.7, c="purple", edgecolors="black"
    )
    pearson_r5, pearson_p5 = stats.pearsonr(val_rmses, final_val_accs)
    # Add trend line
    slope5, intercept5, _, _, _ = stats.linregress(val_rmses, final_val_accs)
    line_x5 = np.linspace(val_rmses.min(), val_rmses.max(), 100)
    ax5.plot(line_x5, slope5 * line_x5 + intercept5, "r--", linewidth=2, alpha=0.8)
    ax5.set_xlabel("Val Loss RMSE (10 epochs)")
    ax5.set_ylabel("Final Val Accuracy")
    ax5.set_title(f"r = {pearson_r5:.3f} (p = {pearson_p5:.3f})")
    ax5.grid(True, alpha=0.3)

    # Val Loss R² vs Val Acc
    ax6 = plt.subplot(3, 3, 6)
    ax6.scatter(
        val_r2s, final_val_accs, s=100, alpha=0.7, c="brown", edgecolors="black"
    )
    pearson_r6, pearson_p6 = stats.pearsonr(val_r2s, final_val_accs)
    # Add trend line
    slope6, intercept6, _, _, _ = stats.linregress(val_r2s, final_val_accs)
    line_x6 = np.linspace(val_r2s.min(), val_r2s.max(), 100)
    ax6.plot(line_x6, slope6 * line_x6 + intercept6, "r--", linewidth=2, alpha=0.8)
    ax6.set_xlabel("Val Loss R² (10 epochs)")
    ax6.set_ylabel("Final Val Accuracy")
    ax6.set_title(f"r = {pearson_r6:.3f} (p = {pearson_p6:.3f})")
    ax6.grid(True, alpha=0.3)

    # Train vs Val Slopes
    ax7 = plt.subplot(3, 3, 7)
    ax7.scatter(
        train_slopes, val_slopes, s=100, alpha=0.7, c="cyan", edgecolors="black"
    )
    pearson_r7, pearson_p7 = stats.pearsonr(train_slopes, val_slopes)
    # Add trend line
    slope7, intercept7, _, _, _ = stats.linregress(train_slopes, val_slopes)
    line_x7 = np.linspace(train_slopes.min(), train_slopes.max(), 100)
    ax7.plot(line_x7, slope7 * line_x7 + intercept7, "r--", linewidth=2, alpha=0.8)
    ax7.set_xlabel("Train Loss Slope")
    ax7.set_ylabel("Val Loss Slope")
    ax7.set_title(f"Train vs Val Slopes\nr = {pearson_r7:.3f}")
    ax7.grid(True, alpha=0.3)

    # Train vs Val RMSE
    ax8 = plt.subplot(3, 3, 8)
    ax8.scatter(
        train_rmses, val_rmses, s=100, alpha=0.7, c="magenta", edgecolors="black"
    )
    pearson_r8, pearson_p8 = stats.pearsonr(train_rmses, val_rmses)
    # Add trend line
    slope8, intercept8, _, _, _ = stats.linregress(train_rmses, val_rmses)
    line_x8 = np.linspace(train_rmses.min(), train_rmses.max(), 100)
    ax8.plot(line_x8, slope8 * line_x8 + intercept8, "r--", linewidth=2, alpha=0.8)
    ax8.set_xlabel("Train Loss RMSE")
    ax8.set_ylabel("Val Loss RMSE")
    ax8.set_title(f"Train vs Val RMSE\nr = {pearson_r8:.3f}")
    ax8.grid(True, alpha=0.3)

    # Train vs Val R²
    ax9 = plt.subplot(3, 3, 9)
    ax9.scatter(train_r2s, val_r2s, s=100, alpha=0.7, c="yellow", edgecolors="black")
    pearson_r9, pearson_p9 = stats.pearsonr(train_r2s, val_r2s)
    # Add trend line
    slope9, intercept9, _, _, _ = stats.linregress(train_r2s, val_r2s)
    line_x9 = np.linspace(train_r2s.min(), train_r2s.max(), 100)
    ax9.plot(line_x9, slope9 * line_x9 + intercept9, "r--", linewidth=2, alpha=0.8)
    ax9.set_xlabel("Train Loss R²")
    ax9.set_ylabel("Val Loss R²")
    ax9.set_title(f"Train vs Val R²\nr = {pearson_r9:.3f}")
    ax9.grid(True, alpha=0.3)

    plt.suptitle(
        "Early Training Dynamics (10 epochs) vs Final Performance", fontsize=16
    )
    plt.tight_layout()
    plt.savefig(
        output_dir / "early_regression_correlation_analysis.png",
        dpi=150,
        bbox_inches="tight",
    )
    plt.close()

    # Create summary table
    summary_data = []
    for i, config in enumerate(config_names):
        summary_data.append(
            {
                "Config": config,
                "Train Slope": train_slopes[i],
                "Train R²": train_r2s[i],
                "Train RMSE": train_rmses[i],
                "Val Slope": val_slopes[i],
                "Val R²": val_r2s[i],
                "Val RMSE": val_rmses[i],
                "Final Val Acc": final_val_accs[i],
            }
        )

    df = pd.DataFrame(summary_data)
    df = df.sort_values("Final Val Acc", ascending=False)
    df.to_csv(
        output_dir / "early_regression_analysis_summary.csv",
        index=False,
        float_format="%.4f",
    )

    # Print summary
    print("\nEarly Training Correlation Analysis (10 epochs):")
    print("=" * 70)
    print(f"{'Metric Pair':<45} {'Pearson r':>10} {'p-value':>10}")
    print("-" * 70)
    print(
        f"{'Train Loss Slope vs Final Val Acc':<45} {pearson_r1:>10.3f} {pearson_p1:>10.3f}"
    )
    print(
        f"{'Train Loss RMSE vs Final Val Acc':<45} {pearson_r2:>10.3f} {pearson_p2:>10.3f}"
    )
    print(
        f"{'Train Loss R² vs Final Val Acc':<45} {pearson_r3:>10.3f} {pearson_p3:>10.3f}"
    )
    print(
        f"{'Val Loss Slope vs Final Val Acc':<45} {pearson_r4:>10.3f} {pearson_p4:>10.3f}"
    )
    print(
        f"{'Val Loss RMSE vs Final Val Acc':<45} {pearson_r5:>10.3f} {pearson_p5:>10.3f}"
    )
    print(
        f"{'Val Loss R² vs Final Val Acc':<45} {pearson_r6:>10.3f} {pearson_p6:>10.3f}"
    )
    print("=" * 70)

    print("\nTop 5 configs by validation accuracy:")
    print(df.head().to_string(index=False))

    return df


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze early regression correlations"
    )
    parser.add_argument("--base-path", type=Path, default=Path("."))
    parser.add_argument("--experiment", type=str, default="cluster_t0")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("./early_correlation_analysis")
    )

    args = parser.parse_args()

    print(f"Loading experiments from {args.base_path / args.experiment}")
    config_results = collect_experiment_data(args.base_path, args.experiment)

    print(f"Found {len(config_results)} configurations")
    print("Analyzing correlations using first 10 epochs only...")
    df = analyze_correlations(config_results, args.output_dir)


if __name__ == "__main__":
    main()
