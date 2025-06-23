#!/usr/bin/env python3
"""Create detailed loss plots with separate panels for each configuration."""

import json
from pathlib import Path
from typing import List, Tuple
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
from collections import defaultdict


def load_metrics_for_run(run_dir: Path) -> Tuple[str, List[float], List[int]]:
    """Load metrics from a single run."""
    job_id = run_dir.name.replace("run_", "")
    job_file = run_dir.parent.parent / "jobs" / f"{job_id}.json"

    config_name = "unknown"
    if job_file.exists():
        with open(job_file, "r") as f:
            job_data = json.load(f)
            config_name = job_data.get("config", {}).get("run_name", "unknown")

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
    """Fit regression line in log-epoch space."""
    valid_indices = [i for i, e in enumerate(epochs) if e > 0]
    if not valid_indices:
        return 0, 0, 0

    x = np.log10([epochs[i] for i in valid_indices])
    y = [losses[i] for i in valid_indices]

    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
    r_squared = r_value**2

    return slope, intercept, r_squared


def main():
    """Create detailed plots."""
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

    # Group configurations by type for better visualization
    config_groups = {
        "Baseline & Optimizers": [
            "step00_baseline",
            "step01_sgd",
            "step05_no_warmup",
            "step06_steplr",
        ],
        "Data Augmentation": [
            "step02_no_randaug",
            "step03_no_cutmix",
            "step04_no_mixup",
            "step15_no_colorjitter",
            "step16_no_rrc",
            "step17_no_hflip",
        ],
        "Architecture": [
            "step07_no_residual",
            "step08_lrn_dropout",
            "step09_xavier",
            "step10_no_lrn",
            "step11_resnet12",
            "step12_alexnet",
            "step13_no_dropout",
            "step14_tanh",
        ],
    }

    # Create plots for each group
    for group_name, configs in config_groups.items():
        # Filter configs
        group_data = {k: v for k, v in config_metrics.items() if k in configs}
        if not group_data:
            continue

        # Create subplot grid
        n_configs = len(group_data)
        n_cols = 3
        n_rows = (n_configs + n_cols - 1) // n_cols

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(15, 4 * n_rows))
        if n_rows == 1:
            axes = axes.reshape(1, -1)

        # Flatten axes for easier iteration
        axes_flat = axes.flatten()

        for idx, (config_name, data) in enumerate(sorted(group_data.items())):
            ax = axes_flat[idx]

            # Calculate mean loss curve
            all_epochs = set()
            for epochs in data["epochs"]:
                all_epochs.update(epochs)
            all_epochs = sorted(list(all_epochs))

            epoch_losses = defaultdict(list)
            for losses, epochs in zip(data["losses"], data["epochs"]):
                for e, l in zip(epochs, losses):
                    epoch_losses[e].append(l)

            mean_epochs = []
            mean_losses = []
            std_losses = []
            for e in all_epochs:
                if e in epoch_losses:
                    mean_epochs.append(e)
                    mean_losses.append(np.mean(epoch_losses[e]))
                    std_losses.append(np.std(epoch_losses[e]))

            # Plot individual runs as thin lines
            for losses, epochs in zip(data["losses"], data["epochs"]):
                ax.plot(epochs, losses, alpha=0.3, color="gray", linewidth=0.5)

            # Plot mean curve
            ax.plot(mean_epochs, mean_losses, "b-", linewidth=2, label="Mean")

            # Add confidence interval
            mean_losses_arr = np.array(mean_losses)
            std_losses_arr = np.array(std_losses)
            ax.fill_between(
                mean_epochs,
                mean_losses_arr - std_losses_arr,
                mean_losses_arr + std_losses_arr,
                alpha=0.2,
                color="blue",
            )

            # Fit and plot regression
            slope, intercept, r_squared = fit_log_regression(mean_epochs, mean_losses)
            if mean_epochs and mean_epochs[0] > 0:
                x_fit = np.logspace(
                    np.log10(max(1, mean_epochs[0])), np.log10(mean_epochs[-1]), 100
                )
                y_fit = slope * np.log10(x_fit) + intercept
                ax.plot(
                    x_fit, y_fit, "r--", linewidth=2, label=f"Fit: slope={slope:.3f}"
                )

            ax.set_xscale("log")
            ax.set_xlabel("Epoch (log scale)")
            ax.set_ylabel("Training Loss")
            ax.set_title(
                f"{config_name}\n(R²={r_squared:.3f}, n={len(data['losses'])})"
            )
            ax.grid(True, alpha=0.3, which="both")
            ax.legend(loc="upper right", fontsize=8)

        # Hide empty subplots
        for idx in range(n_configs, len(axes_flat)):
            axes_flat[idx].set_visible(False)

        plt.suptitle(f"{group_name} - Training Loss Analysis", fontsize=16)
        plt.tight_layout()

        # Save with group name
        filename = group_name.lower().replace(" ", "_").replace("&", "and")
        plt.savefig(
            output_dir / f"training_loss_{filename}.png", dpi=300, bbox_inches="tight"
        )
        plt.close()

    # Create summary comparison plot
    fig, ax = plt.subplots(figsize=(12, 8))

    # Sort configs by slope
    regression_results = []
    for config_name, data in config_metrics.items():
        if not data["losses"]:
            continue

        # Calculate mean curve
        all_epochs = set()
        for epochs in data["epochs"]:
            all_epochs.update(epochs)
        all_epochs = sorted(list(all_epochs))

        epoch_losses = defaultdict(list)
        for losses, epochs in zip(data["losses"], data["epochs"]):
            for e, l in zip(epochs, losses):
                epoch_losses[e].append(l)

        mean_epochs = []
        mean_losses = []
        for e in all_epochs:
            if e in epoch_losses:
                mean_epochs.append(e)
                mean_losses.append(np.mean(epoch_losses[e]))

        slope, intercept, r_squared = fit_log_regression(mean_epochs, mean_losses)
        regression_results.append((config_name, slope, intercept, r_squared))

    # Sort by slope
    regression_results.sort(key=lambda x: x[1], reverse=True)

    # Plot top and bottom performers
    n_show = 6
    colors_top = plt.cm.Reds(np.linspace(0.3, 0.9, n_show))
    colors_bottom = plt.cm.Blues(np.linspace(0.3, 0.9, n_show))

    x_range = np.logspace(0, np.log10(50), 100)

    # Plot worst performers (least negative slope)
    for i, (config_name, slope, intercept, r_squared) in enumerate(
        regression_results[:n_show]
    ):
        if slope != 0:
            y_range = slope * np.log10(x_range) + intercept
            ax.plot(
                x_range,
                y_range,
                color=colors_top[i],
                linewidth=2,
                label=f"{config_name} (slope={slope:.3f})",
            )

    # Plot best performers (most negative slope)
    for i, (config_name, slope, intercept, r_squared) in enumerate(
        regression_results[-n_show:]
    ):
        if slope != 0:
            y_range = slope * np.log10(x_range) + intercept
            ax.plot(
                x_range,
                y_range,
                color=colors_bottom[i],
                linewidth=2,
                label=f"{config_name} (slope={slope:.3f})",
            )

    ax.set_xscale("log")
    ax.set_xlabel("Epoch (log scale)", fontsize=12)
    ax.set_ylabel("Training Loss (from regression)", fontsize=12)
    ax.set_title(
        "Training Loss Regression Comparison\n(Red = Slowest learning, Blue = Fastest learning)",
        fontsize=14,
    )
    ax.grid(True, alpha=0.3, which="both")
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=9)

    plt.tight_layout()
    plt.savefig(
        output_dir / "training_loss_comparison.png", dpi=300, bbox_inches="tight"
    )
    plt.close()

    print(f"\nDetailed plots saved to: {output_dir}")


if __name__ == "__main__":
    main()
