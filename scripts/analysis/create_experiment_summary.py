#!/usr/bin/env python3
"""Create comprehensive experiment summary CSV and subplot grids."""

import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict


def load_metrics(metrics_file: Path) -> List[Dict]:
    """Load metrics from a JSONL file."""
    metrics = []
    with open(metrics_file, "r") as f:
        for line in f:
            data = json.loads(line.strip())
            # Handle both direct metrics and nested format
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

    # Extract base name without _high_reg suffix
    base_name = config_name.replace("_high_reg", "")

    return changes.get(base_name, {})


def collect_experiment_data(base_path: Path, experiment: str) -> pd.DataFrame:
    """Collect all experiment data into a dataframe."""
    exp_dir = base_path / experiment
    storage_dir = exp_dir / "storage"

    # Group results by config
    config_results = defaultdict(list)

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

        # Get config name - look for run_name first, then config_name
        config_name = job["config"].get(
            "run_name", job["config"].get("config_name", "unknown")
        )

        # Load metrics
        metrics_file = run_dir / "metrics.jsonl"
        if not metrics_file.exists():
            continue

        metrics = load_metrics(metrics_file)
        if not metrics:
            continue

        # Get final metrics
        final_metrics = metrics[-1]

        config_results[config_name].append(
            {
                "job_id": job_id,
                "final_train_loss": final_metrics.get("train_loss", np.nan),
                "final_train_acc": final_metrics.get("train_acc", np.nan),
                "final_val_loss": final_metrics.get("val_loss", np.nan),
                "final_val_acc": final_metrics.get("val_acc", np.nan),
                "best_val_acc": max(m.get("val_acc", 0) for m in metrics),
                "epochs": len(metrics),
                "all_metrics": metrics,  # Store for plotting
            }
        )

    # Create summary dataframe
    rows = []
    for config_name, results in config_results.items():
        if not results:
            continue

        # Calculate means and stds
        train_losses = [r["final_train_loss"] for r in results]
        train_accs = [r["final_train_acc"] for r in results]
        val_losses = [r["final_val_loss"] for r in results]
        val_accs = [r["final_val_acc"] for r in results]
        best_val_accs = [r["best_val_acc"] for r in results]

        # Get config changes
        changes = get_config_changes(config_name)

        row = {
            "config": config_name,
            "num_seeds": len(results),
            "train_loss_mean": np.mean(train_losses),
            "train_loss_std": np.std(train_losses),
            "train_acc_mean": np.mean(train_accs),
            "train_acc_std": np.std(train_accs),
            "val_loss_mean": np.mean(val_losses),
            "val_loss_std": np.std(val_losses),
            "val_acc_mean": np.mean(val_accs),
            "val_acc_std": np.std(val_accs),
            "best_val_acc_mean": np.mean(best_val_accs),
            "best_val_acc_std": np.std(best_val_accs),
        }

        # Add config changes as columns
        for key, value in changes.items():
            row[f"change_{key}"] = value

        rows.append(row)

    df = pd.DataFrame(rows)

    # Sort by config name
    df = df.sort_values("config")

    # Store the full results for plotting
    df.attrs["full_results"] = config_results

    return df


def create_subplot_grids(df: pd.DataFrame, output_dir: Path):
    """Create subplot grids for loss and accuracy."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get full results
    config_results = df.attrs["full_results"]

    # Sort configs for consistent ordering
    configs = sorted(config_results.keys())

    # Take first 20 configs (5x4 grid)
    configs = configs[:20]

    # Pad with empty if needed
    while len(configs) < 20:
        configs.append(None)

    # Create figure 1: Loss plots (linear scale)
    fig1, axes1 = plt.subplots(4, 5, figsize=(25, 16), sharex=True, sharey=True)
    fig1.suptitle("Training and Validation Loss - All Experiments", fontsize=16)

    # Create figure 2: Accuracy plots (linear scale)
    fig2, axes2 = plt.subplots(4, 5, figsize=(25, 16), sharex=True, sharey=True)
    fig2.suptitle("Training and Validation Accuracy - All Experiments", fontsize=16)

    # Create figure 3: Loss plots (log x-axis)
    fig3, axes3 = plt.subplots(4, 5, figsize=(25, 16), sharex=True, sharey=True)
    fig3.suptitle(
        "Training and Validation Loss - All Experiments (Log Scale)", fontsize=16
    )

    # Create figure 4: Accuracy plots (log x-axis)
    fig4, axes4 = plt.subplots(4, 5, figsize=(25, 16), sharex=True, sharey=True)
    fig4.suptitle(
        "Training and Validation Accuracy - All Experiments (Log Scale)", fontsize=16
    )

    # Plot each config
    for idx, config in enumerate(configs):
        row = idx // 5
        col = idx % 5

        ax1 = axes1[row, col]
        ax2 = axes2[row, col]
        ax3 = axes3[row, col]
        ax4 = axes4[row, col]

        if config is None or config not in config_results:
            # Empty subplot
            for ax in [ax1, ax2, ax3, ax4]:
                ax.set_visible(False)
            continue

        # Get all runs for this config
        results = config_results[config]

        # Aggregate metrics across seeds
        all_epochs = []
        all_train_losses = []
        all_val_losses = []
        all_train_accs = []
        all_val_accs = []

        for result in results:
            metrics = result["all_metrics"]
            epochs = list(range(len(metrics)))
            train_losses = [m.get("train_loss", np.nan) for m in metrics]
            val_losses = [m.get("val_loss", np.nan) for m in metrics]
            train_accs = [m.get("train_acc", np.nan) for m in metrics]
            val_accs = [m.get("val_acc", np.nan) for m in metrics]

            all_epochs.append(epochs)
            all_train_losses.append(train_losses)
            all_val_losses.append(val_losses)
            all_train_accs.append(train_accs)
            all_val_accs.append(val_accs)

        # Calculate means
        max_len = max(len(e) for e in all_epochs)
        epochs = list(range(max_len))

        # Pad arrays to same length
        def pad_array(arr, length):
            if len(arr) < length:
                return arr + [arr[-1]] * (length - len(arr))
            return arr[:length]

        all_train_losses = [pad_array(arr, max_len) for arr in all_train_losses]
        all_val_losses = [pad_array(arr, max_len) for arr in all_val_losses]
        all_train_accs = [pad_array(arr, max_len) for arr in all_train_accs]
        all_val_accs = [pad_array(arr, max_len) for arr in all_val_accs]

        mean_train_loss = np.mean(all_train_losses, axis=0)
        mean_val_loss = np.mean(all_val_losses, axis=0)
        mean_train_acc = np.mean(all_train_accs, axis=0)
        mean_val_acc = np.mean(all_val_accs, axis=0)

        # Linear scale plots
        ax1.plot(epochs, mean_train_loss, "b-", label="Train", alpha=0.8)
        ax1.plot(epochs, mean_val_loss, "r-", label="Val", alpha=0.8)
        ax1.set_title(config.replace("_", " "), fontsize=10)
        ax1.grid(True, alpha=0.3)
        if row == 0 and col == 0:
            ax1.legend(fontsize=8)

        ax2.plot(epochs, mean_train_acc, "b-", label="Train", alpha=0.8)
        ax2.plot(epochs, mean_val_acc, "r-", label="Val", alpha=0.8)
        ax2.set_title(config.replace("_", " "), fontsize=10)
        ax2.grid(True, alpha=0.3)
        if row == 0 and col == 0:
            ax2.legend(fontsize=8)

        # Log scale plots
        epochs_log = [e + 1 for e in epochs]  # Start from 1 for log scale
        ax3.semilogx(epochs_log, mean_train_loss, "b-", label="Train", alpha=0.8)
        ax3.semilogx(epochs_log, mean_val_loss, "r-", label="Val", alpha=0.8)
        ax3.set_title(config.replace("_", " "), fontsize=10)
        ax3.grid(True, alpha=0.3)
        if row == 0 and col == 0:
            ax3.legend(fontsize=8)

        ax4.semilogx(epochs_log, mean_train_acc, "b-", label="Train", alpha=0.8)
        ax4.semilogx(epochs_log, mean_val_acc, "r-", label="Val", alpha=0.8)
        ax4.set_title(config.replace("_", " "), fontsize=10)
        ax4.grid(True, alpha=0.3)
        if row == 0 and col == 0:
            ax4.legend(fontsize=8)

    # Set common labels
    for ax in axes1[-1, :]:
        ax.set_xlabel("Epoch")
    for ax in axes1[:, 0]:
        ax.set_ylabel("Loss")

    for ax in axes2[-1, :]:
        ax.set_xlabel("Epoch")
    for ax in axes2[:, 0]:
        ax.set_ylabel("Accuracy")

    for ax in axes3[-1, :]:
        ax.set_xlabel("Epoch (log scale)")
    for ax in axes3[:, 0]:
        ax.set_ylabel("Loss")

    for ax in axes4[-1, :]:
        ax.set_xlabel("Epoch (log scale)")
    for ax in axes4[:, 0]:
        ax.set_ylabel("Accuracy")

    # Save figures
    fig1.tight_layout()
    fig1.savefig(output_dir / "loss_grid_linear.png", dpi=150, bbox_inches="tight")

    fig2.tight_layout()
    fig2.savefig(output_dir / "accuracy_grid_linear.png", dpi=150, bbox_inches="tight")

    fig3.tight_layout()
    fig3.savefig(output_dir / "loss_grid_log.png", dpi=150, bbox_inches="tight")

    fig4.tight_layout()
    fig4.savefig(output_dir / "accuracy_grid_log.png", dpi=150, bbox_inches="tight")

    plt.close("all")

    print(f"Saved grid plots to {output_dir}")


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Create experiment summary CSV and plots"
    )
    parser.add_argument("--base-path", type=Path, default=Path("./experiment"))
    parser.add_argument("--experiment", type=str, default="test")
    parser.add_argument("--output-dir", type=Path, default=Path("./experiment_summary"))

    args = parser.parse_args()

    print(f"Analyzing experiments in {args.base_path / args.experiment}")

    # Collect data
    df = collect_experiment_data(args.base_path, args.experiment)

    # Save CSV
    csv_path = args.output_dir / "experiment_summary.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove the full_results attribute before saving
    df_save = df.copy()
    df_save.to_csv(csv_path, index=False, float_format="%.4f")
    print(f"Saved summary CSV to {csv_path}")

    # Create subplot grids
    create_subplot_grids(df, args.output_dir)


if __name__ == "__main__":
    main()
