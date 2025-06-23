#!/usr/bin/env python3
"""Analyze training loss curves for all configurations.

This script:
1. Plots the mean loss curve for each configuration with log-scale epochs and linear loss
2. Fits a regression line to each curve in log-epoch space
3. Reports the slope and intercept for each configuration
"""

import json
from pathlib import Path
from typing import List, Tuple
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
import pandas as pd
from collections import defaultdict


def load_metrics_for_run(run_dir: Path) -> Tuple[str, List[float], List[int]]:
    """Load metrics from a single run.

    Returns:
        Tuple of (config_name, losses, epochs)
    """
    # Get config name from job file
    job_id = run_dir.name.replace("run_", "")
    job_file = run_dir.parent.parent / "jobs" / f"{job_id}.json"

    config_name = "unknown"
    if job_file.exists():
        with open(job_file, "r") as f:
            job_data = json.load(f)
            config_name = job_data.get("config", {}).get("run_name", "unknown")

    # Load metrics
    metrics_file = run_dir / "metrics.jsonl"
    if not metrics_file.exists():
        return config_name, [], []

    losses = []
    epochs = []

    with open(metrics_file, "r") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                metrics = data.get("metrics", {})
                if "train_loss" in metrics and "epoch" in metrics:
                    losses.append(metrics["train_loss"])
                    epochs.append(metrics["epoch"])

    return config_name, losses, epochs


def fit_log_regression(
    epochs: List[int], losses: List[float]
) -> Tuple[float, float, float]:
    """Fit regression line in log-epoch space.

    Returns:
        Tuple of (slope, intercept, r_squared)
    """
    # Filter out epoch 0 to avoid log(0)
    valid_indices = [i for i, e in enumerate(epochs) if e > 0]
    if not valid_indices:
        return 0, 0, 0

    x = np.log10([epochs[i] for i in valid_indices])
    y = [losses[i] for i in valid_indices]

    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
    r_squared = r_value**2

    return slope, intercept, r_squared


def main():
    """Main analysis function."""
    # Set up paths
    storage_dir = Path(
        "/Users/daniellerothermel/drotherm/repos/dr_exp/cluster_t0/storage"
    )
    output_dir = Path(
        "/Users/daniellerothermel/drotherm/repos/dr_exp/presentation_plots"
    )
    output_dir.mkdir(exist_ok=True)

    # Collect all metrics
    config_metrics = defaultdict(lambda: {"losses": [], "epochs": []})

    for run_dir in sorted(storage_dir.glob("run_*")):
        if run_dir.is_dir():
            config_name, losses, epochs = load_metrics_for_run(run_dir)
            if losses and epochs:
                config_metrics[config_name]["losses"].append(losses)
                config_metrics[config_name]["epochs"].append(epochs)

    # Prepare for plotting
    fig, ax = plt.subplots(figsize=(12, 8))

    # Store regression results
    regression_results = []

    # Color map for different configurations
    colors = plt.cm.tab20(np.linspace(0, 1, len(config_metrics)))

    for idx, (config_name, data) in enumerate(sorted(config_metrics.items())):
        if not data["losses"]:
            continue

        # Calculate mean loss curve
        # First, find common epochs across all runs
        all_epochs = set()
        for epochs in data["epochs"]:
            all_epochs.update(epochs)
        all_epochs = sorted(list(all_epochs))

        # Aggregate losses for each epoch
        epoch_losses = defaultdict(list)
        for losses, epochs in zip(data["losses"], data["epochs"]):
            for e, l in zip(epochs, losses):
                epoch_losses[e].append(l)

        # Calculate mean for each epoch
        mean_epochs = []
        mean_losses = []
        for e in all_epochs:
            if e in epoch_losses:
                mean_epochs.append(e)
                mean_losses.append(np.mean(epoch_losses[e]))

        # Plot the mean curve
        color = colors[idx]
        ax.plot(
            mean_epochs,
            mean_losses,
            "o-",
            color=color,
            label=config_name,
            markersize=4,
            linewidth=2,
            alpha=0.8,
        )

        # Fit regression in log-epoch space
        slope, intercept, r_squared = fit_log_regression(mean_epochs, mean_losses)

        # Plot regression line
        if mean_epochs and mean_epochs[0] > 0:
            x_fit = np.logspace(
                np.log10(max(1, mean_epochs[0])), np.log10(mean_epochs[-1]), 100
            )
            y_fit = slope * np.log10(x_fit) + intercept
            ax.plot(x_fit, y_fit, "--", color=color, alpha=0.5, linewidth=1)

        # Store results
        regression_results.append(
            {
                "config": config_name,
                "slope": slope,
                "intercept": intercept,
                "r_squared": r_squared,
                "final_loss": mean_losses[-1] if mean_losses else np.nan,
                "num_runs": len(data["losses"]),
            }
        )

    # Set log scale for x-axis
    ax.set_xscale("log")
    ax.set_xlabel("Epoch (log scale)", fontsize=12)
    ax.set_ylabel("Training Loss", fontsize=12)
    ax.set_title("Training Loss Curves by Configuration", fontsize=14)
    ax.grid(True, alpha=0.3, which="both")

    # Adjust legend
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=8)

    plt.tight_layout()
    plt.savefig(
        output_dir / "training_loss_regression.png", dpi=300, bbox_inches="tight"
    )
    plt.close()

    # Save regression results
    results_df = pd.DataFrame(regression_results)
    results_df = results_df.sort_values("slope", ascending=False)

    # Save to CSV
    results_df.to_csv(output_dir / "regression_analysis_results.csv", index=False)

    # Print results
    print("\nRegression Analysis Results (sorted by slope):")
    print("=" * 80)
    print(
        f"{'Config':<25} {'Slope':>10} {'Intercept':>10} {'R²':>8} {'Final Loss':>10} {'Runs':>5}"
    )
    print("-" * 80)

    for _, row in results_df.iterrows():
        print(
            f"{row['config']:<25} {row['slope']:>10.4f} {row['intercept']:>10.4f} "
            f"{row['r_squared']:>8.4f} {row['final_loss']:>10.4f} {row['num_runs']:>5}"
        )

    # Create a second plot showing just the regression lines
    fig2, ax2 = plt.subplots(figsize=(10, 8))

    for idx, row in results_df.iterrows():
        if row["slope"] != 0:  # Skip configs with no valid regression
            x_range = np.logspace(0, np.log10(50), 100)
            y_range = row["slope"] * np.log10(x_range) + row["intercept"]
            ax2.plot(
                x_range, y_range, label=f"{row['config']} (slope={row['slope']:.3f})"
            )

    ax2.set_xscale("log")
    ax2.set_xlabel("Epoch (log scale)", fontsize=12)
    ax2.set_ylabel("Training Loss (from regression)", fontsize=12)
    ax2.set_title("Training Loss Regression Lines", fontsize=14)
    ax2.grid(True, alpha=0.3, which="both")
    ax2.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=8)

    plt.tight_layout()
    plt.savefig(
        output_dir / "loss_regression_combined.png", dpi=300, bbox_inches="tight"
    )
    plt.close()

    # Save text summary
    with open(output_dir / "regression_analysis_results.txt", "w") as f:
        f.write("Training Loss Regression Analysis Results\n")
        f.write("=" * 80 + "\n")
        f.write("Regression fitted to: loss = slope * log10(epoch) + intercept\n\n")
        f.write(
            f"{'Config':<25} {'Slope':>10} {'Intercept':>10} {'R²':>8} {'Final Loss':>10} {'Runs':>5}\n"
        )
        f.write("-" * 80 + "\n")

        for _, row in results_df.iterrows():
            f.write(
                f"{row['config']:<25} {row['slope']:>10.4f} {row['intercept']:>10.4f} "
                f"{row['r_squared']:>8.4f} {row['final_loss']:>10.4f} {row['num_runs']:>5}\n"
            )

    print(f"\nPlots saved to: {output_dir}")
    print(f"Results saved to: {output_dir / 'regression_analysis_results.csv'}")
    print(f"Text summary saved to: {output_dir / 'regression_analysis_results.txt'}")


if __name__ == "__main__":
    main()
