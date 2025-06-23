#!/usr/bin/env python3
"""Create line plots for experiments using best validation loss."""

import json
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple
import numpy as np
import matplotlib.pyplot as plt


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


def should_include_config(config_name: str) -> bool:
    """Check if config should be included based on name."""
    exclude_patterns = [
        "step08_lrn_dropout",
        "step09_xavier",
        "step10_no_lrn",
        "step11_resnet12",
        "step12_alexnet",
        "step13_no_dropout",
    ]
    return not any(pattern in config_name for pattern in exclude_patterns)


def load_metrics(metrics_file: Path) -> List[Dict]:
    """Load metrics from JSONL file."""
    metrics = []
    with open(metrics_file, "r") as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                if "metrics" in entry:
                    metrics.append(entry["metrics"])
                else:
                    metrics.append(entry)
    return metrics


def collect_experiment_data_v2(base_path: Path, experiment: str) -> Dict[str, List]:
    """Collect all experiment data with proper hyperparameter handling."""
    exp_dir = base_path / experiment
    storage_dir = exp_dir / "storage"
    jobs_dir = exp_dir / "jobs"

    config_results = defaultdict(list)

    # Process all job files to get proper config identifiers
    for job_file in jobs_dir.glob("*.json"):
        with open(job_file, "r") as f:
            job = json.load(f)

        if job["status"] != "completed":
            continue

        config_name = job["config"].get(
            "run_name", job["config"].get("config_name", "unknown")
        )

        if not should_include_config(config_name):
            continue

        # Get unique identifier including hyperparameters
        config_id = get_config_identifier(job)
        config_id = renumber_step_name(config_id)

        # Load metrics
        run_dir = storage_dir / f"run_{job['id']}"
        metrics_file = run_dir / "metrics.jsonl"

        if not metrics_file.exists():
            continue

        metrics = load_metrics(metrics_file)
        if not metrics:
            continue

        config_results[config_id].append(metrics)

    return config_results


def aggregate_metrics(
    results_list: List[List[Dict]],
) -> Tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """Aggregate metrics across seeds with standard deviations."""
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

    std_train_loss = np.std(all_train_losses, axis=0)
    std_val_loss = np.std(all_val_losses, axis=0)
    std_train_acc = np.std(all_train_accs, axis=0)
    std_val_acc = np.std(all_val_accs, axis=0)

    return (
        epochs,
        mean_train_loss,
        mean_val_loss,
        mean_train_acc,
        mean_val_acc,
        std_train_loss,
        std_val_loss,
        std_train_acc,
        std_val_acc,
    )


def get_best_val_loss(config_results: Dict[str, List]) -> Dict[str, float]:
    """Get best (minimum) validation loss for each config."""
    best_losses = {}
    for config, runs in config_results.items():
        val_losses = []
        for metrics in runs:
            if metrics:
                # Find minimum validation loss across all epochs
                min_loss = min(m.get("val_loss", float("inf")) for m in metrics)
                val_losses.append(min_loss)
        best_losses[config] = np.mean(val_losses) if val_losses else float("inf")
    return best_losses


def create_line_plots_v2(config_results: Dict[str, List], output_dir: Path):
    """Create line plots with proper hyperparameter handling."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get best losses for sorting (lower is better)
    best_losses = get_best_val_loss(config_results)

    # Sort configs by best loss (ascending - lower is better)
    sorted_configs = sorted(config_results.keys(), key=lambda x: best_losses[x])

    # Color setup
    num_configs = len(sorted_configs)
    if num_configs <= 20:
        colors = plt.cm.tab20(np.linspace(0, 1, num_configs))
    else:
        # Use multiple colormaps for more configs
        colors1 = plt.cm.tab20(np.linspace(0, 1, 20))
        colors2 = plt.cm.tab20b(np.linspace(0, 1, 20))
        colors3 = plt.cm.tab20c(np.linspace(0, 1, 20))
        all_colors = np.vstack([colors1, colors2, colors3])
        colors = all_colors[:num_configs]

    # Create label shortener function
    def shorten_label(config):
        if len(config) > 30:
            # Shorten long configs
            if "controlled" in config:
                config = config.replace("controlled_", "ctrl_")
            if "baseline" in config:
                config = config.replace("baseline", "base")
            if "_no_" in config:
                config = config.replace("_no_", "_n")
        return config

    # 1. Top performers plot (best config per type)
    # Group configs by base type
    config_groups = defaultdict(list)
    for config in sorted_configs:
        # Extract base config name
        base = config.split("_lr")[0].split("_wd")[0]
        config_groups[base].append(config)

    # Plot best from each group
    plotted_configs = []
    for base, configs in sorted(config_groups.items()):
        # Get best config from this group (lowest loss)
        best_config = min(configs, key=lambda x: best_losses[x])
        plotted_configs.append(best_config)

    # Sort by loss (ascending) and plot top 20
    plotted_configs.sort(key=lambda x: best_losses[x])
    plotted_configs = plotted_configs[:20]

    # Create both full range and zoomed versions for validation loss
    for zoom_type in ["full", "zoomed"]:
        plt.figure(figsize=(14, 10))

        min_loss = float("inf")
        max_loss = 0.0

        for i, config in enumerate(plotted_configs):
            epochs, _, mean_val_loss, _, _, _, std_val_loss, _, _ = aggregate_metrics(
                config_results[config]
            )
            label = f"{shorten_label(config)} (best: {best_losses[config]:.4f})"

            plt.plot(epochs, mean_val_loss, label=label, linewidth=2, alpha=0.8)
            plt.fill_between(
                epochs,
                mean_val_loss - std_val_loss,
                mean_val_loss + std_val_loss,
                alpha=0.2,
            )

            # Track min/max for zooming
            min_loss = min(min_loss, np.min(mean_val_loss - std_val_loss))
            max_loss = max(max_loss, np.max(mean_val_loss + std_val_loss))

        plt.xlabel("Epoch", fontsize=12)
        plt.ylabel("Validation Loss", fontsize=12)
        plt.title("Top Performers - Best Val Loss per Config Type", fontsize=14)
        plt.grid(True, alpha=0.3)
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=9)

        if zoom_type == "zoomed":
            # Add 5% padding
            padding = (max_loss - min_loss) * 0.05
            plt.ylim(min_loss - padding, max_loss + padding)

        plt.tight_layout()
        plt.savefig(
            output_dir / f"best_per_config_type_best_val_loss_{zoom_type}.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close()

    # 2. All configs plot (showing hyperparameter variations)
    # Create both full range and zoomed versions
    for zoom_type in ["full", "zoomed"]:
        plt.figure(figsize=(16, 12))

        min_loss = float("inf")
        max_loss = 0.0

        for i, config in enumerate(sorted_configs):
            epochs, _, mean_val_loss, _, _, _, std_val_loss, _, _ = aggregate_metrics(
                config_results[config]
            )
            label = f"{shorten_label(config)} (best: {best_losses[config]:.4f})"

            line = plt.plot(
                epochs,
                mean_val_loss,
                label=label,
                color=colors[i % len(colors)],
                linewidth=1.5,
                alpha=0.7,
            )[0]
            plt.fill_between(
                epochs,
                mean_val_loss - std_val_loss,
                mean_val_loss + std_val_loss,
                color=line.get_color(),
                alpha=0.1,
            )

            # Track min/max for zooming
            min_loss = min(min_loss, np.min(mean_val_loss - std_val_loss))
            max_loss = max(max_loss, np.max(mean_val_loss + std_val_loss))

        plt.xlabel("Epoch", fontsize=12)
        plt.ylabel("Validation Loss", fontsize=12)
        plt.title(
            f"All Configurations - Sorted by Best Val Loss ({num_configs} configs)",
            fontsize=14,
        )
        plt.grid(True, alpha=0.3)
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=7, ncol=2)

        if zoom_type == "zoomed":
            # Add 5% padding
            padding = (max_loss - min_loss) * 0.05
            plt.ylim(min_loss - padding, max_loss + padding)

        plt.tight_layout()
        plt.savefig(
            output_dir / f"all_configs_best_val_loss_{zoom_type}.png",
            dpi=150,
            bbox_inches="tight",
        )
        plt.close()

    # 3. Hyperparameter comparison plots
    # Compare different learning rates for same config
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # SGD lr comparison - loss plot
    ax = axes[0, 0]
    sgd_configs = [
        c for c in sorted_configs if "step01_sgd" in c or "step02" in c or "step03" in c
    ]
    for config in sgd_configs[:10]:  # Limit to 10 for clarity
        epochs, _, mean_val_loss, _, _, _, std_val_loss, _, _ = aggregate_metrics(
            config_results[config]
        )
        label = f"{shorten_label(config)} (best: {best_losses[config]:.4f})"
        line = ax.plot(epochs, mean_val_loss, label=label, linewidth=2, alpha=0.8)[0]
        ax.fill_between(
            epochs,
            mean_val_loss - std_val_loss,
            mean_val_loss + std_val_loss,
            color=line.get_color(),
            alpha=0.2,
        )
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Validation Loss")
    ax.set_title("SGD Learning Rate Comparison (Val Loss)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    # AdamW hyperparameter comparison - loss plot
    ax = axes[0, 1]
    adamw_configs = [c for c in sorted_configs if "step00_baseline" in c]
    for config in adamw_configs:
        epochs, _, mean_val_loss, _, _, _, std_val_loss, _, _ = aggregate_metrics(
            config_results[config]
        )
        label = f"{shorten_label(config)} (best: {best_losses[config]:.4f})"
        line = ax.plot(epochs, mean_val_loss, label=label, linewidth=2, alpha=0.8)[0]
        ax.fill_between(
            epochs,
            mean_val_loss - std_val_loss,
            mean_val_loss + std_val_loss,
            color=line.get_color(),
            alpha=0.2,
        )
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Validation Loss")
    ax.set_title("AdamW Hyperparameter Comparison (Val Loss)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    # Controlled experiments - loss plot
    ax = axes[1, 0]
    controlled_configs = [c for c in sorted_configs if "controlled" in c]
    for config in controlled_configs:
        epochs, _, mean_val_loss, _, _, _, std_val_loss, _, _ = aggregate_metrics(
            config_results[config]
        )
        label = f"{shorten_label(config)} (best: {best_losses[config]:.4f})"
        line = ax.plot(epochs, mean_val_loss, label=label, linewidth=2, alpha=0.8)[0]
        ax.fill_between(
            epochs,
            mean_val_loss - std_val_loss,
            mean_val_loss + std_val_loss,
            color=line.get_color(),
            alpha=0.2,
        )
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Validation Loss")
    ax.set_title("Controlled Experiments - Val Loss")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    # Learning rate impact across steps - bar chart
    ax = axes[1, 1]
    # Compare lr=0.1 vs lr=0.05 for various steps
    pairs = [
        ("step01_sgd", "step01_sgd_lr-0.05"),
        ("step02_no_randaug", "step02_no_randaug_lr-0.05"),
        ("step04_no_mixup", "step04_no_mixup_lr-0.05"),
    ]

    x_pos = np.arange(len(pairs))
    lr_default = []
    lr_lower = []

    for default, lower in pairs:
        if default in best_losses and lower in best_losses:
            lr_default.append(best_losses[default])
            lr_lower.append(best_losses[lower])
        else:
            lr_default.append(float("inf"))
            lr_lower.append(float("inf"))

    width = 0.35
    ax.bar(x_pos - width / 2, lr_default, width, label="lr=0.1 (default)", alpha=0.8)
    ax.bar(x_pos + width / 2, lr_lower, width, label="lr=0.05", alpha=0.8)
    ax.set_xlabel("Configuration")
    ax.set_ylabel("Best Validation Loss")
    ax.set_title("Learning Rate Impact on Best Loss (Lower is Better)")
    ax.set_xticks(x_pos)
    ax.set_xticklabels(
        [p[0].replace("step0", "s").replace("_", " ") for p in pairs], rotation=45
    )
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    plt.savefig(
        output_dir / "hyperparameter_comparisons_best_loss.png",
        dpi=150,
        bbox_inches="tight",
    )
    plt.close()

    print(f"Created plots in {output_dir}")
    print(
        "- best_per_config_type_best_val_loss_full.png: Best hyperparameters (full y-axis)"
    )
    print(
        "- best_per_config_type_best_val_loss_zoomed.png: Best hyperparameters (zoomed y-axis)"
    )
    print(
        f"- all_configs_best_val_loss_full.png: All {num_configs} configurations (full y-axis)"
    )
    print(
        f"- all_configs_best_val_loss_zoomed.png: All {num_configs} configurations (zoomed y-axis)"
    )
    print(
        "- hyperparameter_comparisons_best_loss.png: Detailed hyperparameter impact analysis"
    )


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Create line plots using best validation loss"
    )
    parser.add_argument("--base-path", type=Path, default=Path("."))
    parser.add_argument("--experiment", type=str, default="cluster_t0")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("./na_full_t1_best_loss/01_line_plots")
    )

    args = parser.parse_args()

    print(f"Loading experiments from {args.base_path / args.experiment}")
    config_results = collect_experiment_data_v2(args.base_path, args.experiment)

    print(
        f"Found {len(config_results)} unique configurations (with hyperparameter variations)"
    )
    create_line_plots_v2(config_results, args.output_dir)


if __name__ == "__main__":
    main()
