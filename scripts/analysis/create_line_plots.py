#!/usr/bin/env python3
"""Create line plots for experiment results - both all configs and grouped."""

import json
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict


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


def collect_experiment_data(base_path: Path, experiment: str) -> Dict[str, Dict]:
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


def aggregate_metrics(
    results_list: List[List[Dict]],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Aggregate metrics across seeds."""
    max_len = max(len(metrics) for metrics in results_list)
    epochs = np.arange(max_len)

    # Initialize arrays
    all_train_losses = []
    all_val_losses = []
    all_train_accs = []
    all_val_accs = []

    for metrics in results_list:
        train_losses = [m.get("train_loss", np.nan) for m in metrics]
        val_losses = [m.get("val_loss", np.nan) for m in metrics]
        train_accs = [m.get("train_acc", np.nan) for m in metrics]
        val_accs = [m.get("val_acc", np.nan) for m in metrics]

        # Pad to max length
        if len(train_losses) < max_len:
            train_losses.extend([train_losses[-1]] * (max_len - len(train_losses)))
            val_losses.extend([val_losses[-1]] * (max_len - len(val_losses)))
            train_accs.extend([train_accs[-1]] * (max_len - len(train_accs)))
            val_accs.extend([val_accs[-1]] * (max_len - len(val_accs)))

        all_train_losses.append(train_losses)
        all_val_losses.append(val_losses)
        all_train_accs.append(train_accs)
        all_val_accs.append(val_accs)

    # Calculate means and stds
    mean_train_loss = np.mean(all_train_losses, axis=0)
    mean_val_loss = np.mean(all_val_losses, axis=0)
    mean_train_acc = np.mean(all_train_accs, axis=0)
    mean_val_acc = np.mean(all_val_accs, axis=0)

    return epochs, mean_train_loss, mean_val_loss, mean_train_acc, mean_val_acc


def create_plots(config_results: Dict[str, List], output_dir: Path):
    """Create all requested plots."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Sort configs by name
    sorted_configs = sorted(config_results.keys())

    # Color palette - use a colormap with enough distinct colors
    num_configs = len(sorted_configs)
    if num_configs <= 20:
        colors = plt.cm.tab20(np.linspace(0, 1, num_configs))
    else:
        # Use a combination of colormaps for more than 20 configs
        colors1 = plt.cm.tab20(np.linspace(0, 1, 20))
        colors2 = plt.cm.tab20b(np.linspace(0, 1, 20))
        colors3 = plt.cm.tab20c(np.linspace(0, 1, 20))
        all_colors = np.vstack([colors1, colors2, colors3])
        colors = all_colors[:num_configs]

    # Create config labels
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

    # 1. All lines - Validation Accuracy (linear epochs)
    plt.figure(figsize=(14, 10))
    for i, config in enumerate(sorted_configs):
        epochs, _, _, _, mean_val_acc = aggregate_metrics(config_results[config])
        label = config_labels.get(config, config)
        plt.plot(
            epochs,
            mean_val_acc,
            label=label,
            color=colors[i % len(colors)],
            linewidth=1.5,
            alpha=0.8,
        )

    plt.xlabel("Epoch", fontsize=12)
    plt.ylabel("Validation Accuracy", fontsize=12)
    plt.title(
        f"All Experiments - Validation Accuracy ({num_configs} configs)", fontsize=14
    )
    plt.grid(True, alpha=0.3)
    plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=10)
    plt.tight_layout()
    plt.savefig(output_dir / "all_val_acc_linear.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 2. All lines - Validation Loss (linear epochs)
    plt.figure(figsize=(14, 10))
    for i, config in enumerate(sorted_configs):
        epochs, _, mean_val_loss, _, _ = aggregate_metrics(config_results[config])
        label = config_labels.get(config, config)
        plt.plot(
            epochs,
            mean_val_loss,
            label=label,
            color=colors[i % len(colors)],
            linewidth=1.5,
            alpha=0.8,
        )

    plt.xlabel("Epoch", fontsize=12)
    plt.ylabel("Validation Loss", fontsize=12)
    plt.title(f"All Experiments - Validation Loss ({num_configs} configs)", fontsize=14)
    plt.grid(True, alpha=0.3)
    plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=10)
    plt.tight_layout()
    plt.savefig(output_dir / "all_val_loss_linear.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 3. All lines - Validation Loss (log epochs)
    plt.figure(figsize=(14, 10))
    for i, config in enumerate(sorted_configs):
        epochs, _, mean_val_loss, _, _ = aggregate_metrics(config_results[config])
        label = config_labels.get(config, config)
        plt.semilogx(
            epochs + 1,
            mean_val_loss,
            label=label,
            color=colors[i % len(colors)],
            linewidth=1.5,
            alpha=0.8,
        )

    plt.xlabel("Epoch (log scale)", fontsize=12)
    plt.ylabel("Validation Loss", fontsize=12)
    plt.title(
        f"All Experiments - Validation Loss (Log Scale) ({num_configs} configs)",
        fontsize=14,
    )
    plt.grid(True, alpha=0.3)
    plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=10)
    plt.tight_layout()
    plt.savefig(output_dir / "all_val_loss_log.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Now create grouped plots
    # Group by category if we have many configs
    if num_configs > 20:
        # Create groups based on config names
        groups = []
        controlled = [c for c in sorted_configs if "controlled" in c]
        adamw_sweep = [
            c for c in sorted_configs if "step00" in c and ("lr" in c or "wd" in c)
        ]
        sgd_sweep = [
            c
            for c in sorted_configs
            if any(f"step{i:02d}" in c for i in range(1, 18)) and "lr" in c
        ]
        regular_steps = [
            c for c in sorted_configs if c not in controlled + adamw_sweep + sgd_sweep
        ]

        if controlled:
            groups.append(("Controlled Experiments", controlled[:10]))
        if adamw_sweep:
            groups.append(("AdamW Hyperparameter Sweep", adamw_sweep[:10]))
        if sgd_sweep:
            groups.append(("SGD Hyperparameter Sweep", sgd_sweep[:10]))
        if regular_steps:
            groups.append(("Regular Step Experiments", regular_steps[:15]))
    else:
        # Original grouping for smaller number of configs
        groups_per_plot = 5
        num_groups = (num_configs + groups_per_plot - 1) // groups_per_plot
        groups = []
        for g in range(num_groups):
            start_idx = g * groups_per_plot
            end_idx = min((g + 1) * groups_per_plot, num_configs)
            group_configs = sorted_configs[start_idx:end_idx]
            groups.append(
                (f"Group {g + 1}: Configs {start_idx + 1}-{end_idx}", group_configs)
            )

    for group_idx, (group_name, group_configs) in enumerate(groups):
        # Grouped Validation Accuracy (linear)
        plt.figure(figsize=(10, 6))
        for i, config in enumerate(group_configs):
            epochs, _, _, _, mean_val_acc = aggregate_metrics(config_results[config])
            label = config_labels.get(config, config)
            color_idx = sorted_configs.index(config)
            plt.plot(
                epochs,
                mean_val_acc,
                label=label,
                color=colors[color_idx % len(colors)],
                linewidth=2,
                alpha=0.9,
            )

        plt.xlabel("Epoch", fontsize=12)
        plt.ylabel("Validation Accuracy", fontsize=12)
        plt.title(f"{group_name} - Validation Accuracy", fontsize=14)
        plt.grid(True, alpha=0.3)
        plt.legend(fontsize=11)
        plt.tight_layout()
        plt.savefig(
            output_dir / f"group{group_idx + 1}_val_acc_linear.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close()

        # Grouped Validation Loss (linear)
        plt.figure(figsize=(10, 6))
        for i, config in enumerate(group_configs):
            epochs, _, mean_val_loss, _, _ = aggregate_metrics(config_results[config])
            label = config_labels.get(config, config)
            color_idx = sorted_configs.index(config)
            plt.plot(
                epochs,
                mean_val_loss,
                label=label,
                color=colors[color_idx % len(colors)],
                linewidth=2,
                alpha=0.9,
            )

        plt.xlabel("Epoch", fontsize=12)
        plt.ylabel("Validation Loss", fontsize=12)
        plt.title(f"{group_name} - Validation Loss", fontsize=14)
        plt.grid(True, alpha=0.3)
        plt.legend(fontsize=11)
        plt.tight_layout()
        plt.savefig(
            output_dir / f"group{group_idx + 1}_val_loss_linear.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close()

        # Grouped Validation Loss (log)
        plt.figure(figsize=(10, 6))
        for i, config in enumerate(group_configs):
            epochs, _, mean_val_loss, _, _ = aggregate_metrics(config_results[config])
            label = config_labels.get(config, config)
            color_idx = sorted_configs.index(config)
            plt.semilogx(
                epochs + 1,
                mean_val_loss,
                label=label,
                color=colors[color_idx % len(colors)],
                linewidth=2,
                alpha=0.9,
            )

        plt.xlabel("Epoch (log scale)", fontsize=12)
        plt.ylabel("Validation Loss", fontsize=12)
        plt.title(f"{group_name} - Validation Loss (Log Scale)", fontsize=14)
        plt.grid(True, alpha=0.3)
        plt.legend(fontsize=11)
        plt.tight_layout()
        plt.savefig(
            output_dir / f"group{group_idx + 1}_val_loss_log.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close()

    print(f"Created plots in {output_dir}")
    print(
        f"- All {num_configs} configs: all_val_acc_linear.png, all_val_loss_linear.png, all_val_loss_log.png"
    )
    for i, (group_name, _) in enumerate(groups):
        print(f"- {group_name}: group{i + 1}_*.png")


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Create line plots for experiments")
    parser.add_argument("--base-path", type=Path, default=Path("."))
    parser.add_argument("--experiment", type=str, default="cluster_t0")
    parser.add_argument("--output-dir", type=Path, default=Path("./line_plots"))

    args = parser.parse_args()

    print(f"Loading experiments from {args.base_path / args.experiment}")
    config_results = collect_experiment_data(args.base_path, args.experiment)

    print(f"Found {len(config_results)} configurations")
    create_plots(config_results, args.output_dir)


if __name__ == "__main__":
    main()
