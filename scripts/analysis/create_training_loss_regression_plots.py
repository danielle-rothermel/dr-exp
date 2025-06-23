#!/usr/bin/env python3
"""Create grouped training loss plots with log epochs and regression lines."""

import json
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict
from scipy import stats


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
        "step11": "step08",  # ResNet12
        "step12": "step09",  # AlexNet
        "step13": "step10",  # No dropout
        "step14": "step11",  # Tanh
        "step15": "step12",  # No colorjitter
        "step16": "step13",  # No RRC
        "step17": "step14",  # No hflip
    }

    for old_step, new_step in renumber_map.items():
        if config_name.startswith(old_step):
            return config_name.replace(old_step, new_step, 1)

    return config_name


def collect_experiment_data(base_path: Path, experiment: str) -> Dict[str, List]:
    """Collect all experiment data."""
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
        config_results[display_name].append(metrics)

    return config_results


def aggregate_train_loss(
    results_list: List[List[Dict]],
) -> Tuple[np.ndarray, np.ndarray]:
    """Aggregate training loss across seeds."""
    max_len = max(len(metrics) for metrics in results_list)
    epochs = np.arange(max_len)

    all_train_losses = []

    for metrics in results_list:
        train_losses = [m.get("train_loss", np.nan) for m in metrics]

        # Pad to max length
        if len(train_losses) < max_len:
            train_losses.extend([train_losses[-1]] * (max_len - len(train_losses)))

        all_train_losses.append(train_losses)

    mean_train_loss = np.mean(all_train_losses, axis=0)

    return epochs, mean_train_loss


def fit_regression(
    epochs: np.ndarray, losses: np.ndarray, max_epoch: int = 25
) -> Tuple[float, float, float]:
    """Fit linear regression to log(epoch) vs loss for first max_epoch epochs."""
    # Filter to first max_epoch epochs
    mask = epochs < max_epoch
    epochs_subset = epochs[mask] + 1  # Add 1 to avoid log(0)
    losses_subset = losses[mask]

    # Remove any NaN values
    valid_mask = ~np.isnan(losses_subset)
    epochs_subset = epochs_subset[valid_mask]
    losses_subset = losses_subset[valid_mask]

    if len(epochs_subset) < 2:
        return np.nan, np.nan, np.nan

    # Fit linear regression on log(epoch) vs loss
    log_epochs = np.log(epochs_subset)
    slope, intercept, r_value, p_value, std_err = stats.linregress(
        log_epochs, losses_subset
    )

    return slope, intercept, r_value


def create_grouped_plots(config_results: Dict[str, List], output_dir: Path):
    """Create grouped training loss plots with regression lines."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Sort configs by name
    sorted_configs = sorted(config_results.keys())

    # Color palette
    colors = plt.cm.tab20(np.linspace(0, 1, 15))

    # Config labels
    config_labels = {
        "step00_baseline": "00: Baseline",
        "step01_sgd": "01: SGD",
        "step02_no_randaug": "02: No RandAug",
        "step03_no_cutmix": "03: No CutMix",
        "step04_no_mixup": "04: No Mixup",
        "step05_no_warmup": "05: No Warmup",
        "step06_steplr": "06: StepLR",
        "step07_no_residual": "07: No Residual",
        "step08_resnet12": "08: ResNet12",
        "step09_alexnet": "09: AlexNet",
        "step10_no_dropout": "10: No Dropout",
        "step11_tanh": "11: Tanh",
        "step12_no_colorjitter": "12: No ColorJitter",
        "step13_no_rrc": "13: No RRC",
        "step14_no_hflip": "14: No HFlip",
    }

    # Groups
    groups = [
        ("Group 1: Baseline & Core Changes", sorted_configs[0:5]),
        ("Group 2: Scheduler & Architecture", sorted_configs[5:10]),
        ("Group 3: Activation & Aug Details", sorted_configs[10:15]),
    ]

    # Create figure for all groups
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    for group_idx, (group_name, group_configs) in enumerate(groups):
        ax = axes[group_idx]

        # Store regression info for legend
        regression_info = []

        for i, config in enumerate(group_configs):
            epochs, mean_train_loss = aggregate_train_loss(config_results[config])
            label = config_labels.get(config, config)
            color_idx = sorted_configs.index(config)

            # Plot training loss on log scale
            ax.semilogx(
                epochs + 1,
                mean_train_loss,
                color=colors[color_idx],
                linewidth=2,
                alpha=0.7,
                label=label,
            )

            # Fit regression on first 25 epochs
            slope, intercept, r_value = fit_regression(
                epochs, mean_train_loss, max_epoch=25
            )

            if not np.isnan(slope):
                # Plot regression line on log scale
                # Since we're on a log scale, the line equation is: loss = slope * log(epoch) + intercept
                # We need to plot this across the full range, not just 1-25
                epochs_line = np.logspace(0, np.log10(50), 100)  # 1 to 50 in log space
                regression_line = slope * np.log(epochs_line) + intercept
                # Only show the line up to epoch 25 for clarity
                mask = epochs_line <= 25
                ax.plot(
                    epochs_line[mask],
                    regression_line[mask],
                    color=colors[color_idx],
                    linestyle="--",
                    linewidth=1.5,
                    alpha=0.8,
                )

                # Store regression info
                regression_info.append(
                    f"{label}: slope={slope:.3f}, R²={r_value**2:.3f}"
                )

        # Styling
        ax.set_xlabel("Epoch (log scale)", fontsize=12)
        ax.set_ylabel("Training Loss", fontsize=12)
        ax.set_title(f"{group_name}", fontsize=13)
        ax.grid(True, alpha=0.3, which="both")
        ax.set_xlim(1, 50)

        # Add vertical line at epoch 25
        ax.axvline(x=25, color="gray", linestyle=":", alpha=0.5)
        ax.text(
            25,
            ax.get_ylim()[1] * 0.95,
            "Regression fit →",
            ha="right",
            va="top",
            fontsize=8,
            alpha=0.7,
        )

        # Legend
        ax.legend(fontsize=9, loc="upper right")

    plt.suptitle(
        "Training Loss with Log-Linear Regression (First 25 Epochs)", fontsize=14
    )
    plt.tight_layout()
    plt.savefig(
        output_dir / "grouped_train_loss_regression.png", dpi=150, bbox_inches="tight"
    )
    plt.close()

    # Create individual plots with regression statistics
    for group_idx, (group_name, group_configs) in enumerate(groups):
        plt.figure(figsize=(10, 8))

        regression_stats = []

        for i, config in enumerate(group_configs):
            epochs, mean_train_loss = aggregate_train_loss(config_results[config])
            label = config_labels.get(config, config)
            color_idx = sorted_configs.index(config)

            # Plot training loss
            plt.semilogx(
                epochs + 1,
                mean_train_loss,
                color=colors[color_idx],
                linewidth=2.5,
                alpha=0.8,
                label=label,
            )

            # Fit and plot regression
            slope, intercept, r_value = fit_regression(
                epochs, mean_train_loss, max_epoch=25
            )

            if not np.isnan(slope):
                # Plot regression line on log scale
                epochs_line = np.logspace(0, np.log10(25), 100)  # 1 to 25 in log space
                regression_line = slope * np.log(epochs_line) + intercept
                plt.plot(
                    epochs_line,
                    regression_line,
                    color=colors[color_idx],
                    linestyle="--",
                    linewidth=2,
                    alpha=0.9,
                )

                regression_stats.append((label, slope, r_value**2))

        plt.xlabel("Epoch (log scale)", fontsize=14)
        plt.ylabel("Training Loss", fontsize=14)
        plt.title(
            f"{group_name}\nTraining Loss with Log-Linear Regression", fontsize=16
        )
        plt.grid(True, alpha=0.3, which="both")
        plt.xlim(1, 50)

        # Add regression statistics box
        stats_text = "Regression Statistics (epochs 1-25):\n"
        stats_text += "-" * 35 + "\n"
        for label, slope, r2 in regression_stats:
            stats_text += f"{label:<20} slope: {slope:6.3f}, R²: {r2:.3f}\n"

        plt.text(
            0.02,
            0.02,
            stats_text,
            transform=plt.gca().transAxes,
            fontsize=10,
            fontfamily="monospace",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8),
            verticalalignment="bottom",
        )

        # Add vertical line at epoch 25
        plt.axvline(x=25, color="gray", linestyle=":", alpha=0.5, linewidth=2)
        plt.text(
            25,
            plt.gca().get_ylim()[1] * 0.95,
            "← Regression fit range",
            ha="left",
            va="top",
            fontsize=10,
            alpha=0.7,
        )

        plt.legend(fontsize=12, loc="upper right")
        plt.tight_layout()
        plt.savefig(
            output_dir / f"group{group_idx + 1}_train_loss_regression_detailed.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close()

    print(f"Created regression plots in {output_dir}")
    print("- grouped_train_loss_regression.png (all groups)")
    print(
        "- group[1-3]_train_loss_regression_detailed.png (individual groups with stats)"
    )


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Create training loss regression plots"
    )
    parser.add_argument("--base-path", type=Path, default=Path("."))
    parser.add_argument("--experiment", type=str, default="cluster_t0")
    parser.add_argument("--output-dir", type=Path, default=Path("./regression_plots"))

    args = parser.parse_args()

    print(f"Loading experiments from {args.base_path / args.experiment}")
    config_results = collect_experiment_data(args.base_path, args.experiment)

    print(f"Found {len(config_results)} configurations")
    create_grouped_plots(config_results, args.output_dir)


if __name__ == "__main__":
    main()
