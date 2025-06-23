#!/usr/bin/env python3
"""Analyze and plot metrics from completed experiments with sophisticated config handling."""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set
from collections import defaultdict
import hashlib

import matplotlib.pyplot as plt
import numpy as np


class MetricsAnalyzer:
    """Analyze metrics from dr_exp experiments."""

    def __init__(self, base_path: Path, experiment: str):
        self.base_path = base_path
        self.experiment = experiment
        self.experiment_path = base_path / experiment
        self.jobs_dir = self.experiment_path / "jobs"
        self.storage_dir = self.experiment_path / "storage"

    def load_completed_jobs(self) -> List[Dict[str, Any]]:
        """Load all completed jobs with their metrics."""
        completed_jobs = []

        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file) as f:
                    job = json.load(f)

                if job["status"] != "completed":
                    continue

                # Load metrics
                job_id = job["id"]
                metrics_file = self.storage_dir / f"run_{job_id}" / "metrics.jsonl"

                if metrics_file.exists():
                    # Parse JSON Lines format
                    metrics = {}
                    with open(metrics_file) as f:
                        for line in f:
                            if line.strip():
                                entry = json.loads(line)
                                epoch = entry["metrics"]["epoch"]
                                # Store metrics by epoch
                                metrics[str(epoch)] = entry["metrics"]

                    job["metrics_data"] = metrics
                    completed_jobs.append(job)
                else:
                    print(f"Warning: No metrics found for completed job {job_id}")

            except Exception as e:
                print(f"Error loading job {job_file}: {e}")

        return completed_jobs

    def get_config_signature(
        self, job: Dict[str, Any], exclude_params: Optional[Set[str]] = None
    ) -> str:
        """Create a unique identifier for a config (excluding seed and other params)."""
        config = job["config"].copy()

        # Default exclusions - expanded to include run-specific params
        default_exclude = {
            "seed",
            "_target_",
            "hydra",
            "paths.run_dir",  # This changes per run
            "paths.logs",  # Might have timestamp
            "paths.my_logs",  # Might have timestamp
        }
        exclude = default_exclude | (exclude_params or set())

        # Remove excluded params (handle nested params)
        for param in exclude:
            if "." in param:
                # Handle nested params like paths.run_dir
                parts = param.split(".")
                try:
                    obj = config
                    for part in parts[:-1]:
                        obj = obj[part]
                    obj.pop(parts[-1], None)
                except (KeyError, TypeError):
                    pass
            else:
                config.pop(param, None)

        # Create deterministic string representation
        config_str = json.dumps(config, sort_keys=True)
        # Use hash for shorter signature
        return hashlib.md5(config_str.encode()).hexdigest()[:12]

    def detect_overrides(
        self, config: Dict[str, Any], base_configs: Optional[Dict[str, Dict]] = None
    ) -> List[Tuple[str, Any]]:
        """Auto-detect important overrides in config."""
        # Key parameters to always show if they differ
        important_params = {
            "lr",
            "learning_rate",
            "batch_size",
            "epochs",
            "optimizer",
            "optimizer.name",
            "optimizer.lr",
            "optimizer.weight_decay",
            "model",
            "model.name",
            "weight_decay",
            "wd",
        }

        overrides = []

        # Get config name
        config_name = config.get("config_name", config.get("run_name", "custom"))

        # If we have base configs, compare against base
        if base_configs and config_name in base_configs:
            base = base_configs[config_name]
            for key in important_params:
                if "." in key:
                    # Handle nested keys
                    parts = key.split(".")
                    val = config
                    base_val = base
                    try:
                        for part in parts:
                            val = val.get(part, {})
                            base_val = base_val.get(part, {})
                        if val != base_val and val != {}:
                            overrides.append((key, val))
                    except:
                        pass
                else:
                    if key in config and config.get(key) != base.get(key):
                        overrides.append((key, config[key]))
        else:
            # No base config, just show important params that exist
            for key in ["lr", "learning_rate", "batch_size", "optimizer.name"]:
                if "." in key:
                    parts = key.split(".")
                    val = config
                    try:
                        for part in parts:
                            val = val.get(part, {})
                        if val and val != {}:
                            overrides.append((key, val))
                    except:
                        pass
                elif key in config:
                    overrides.append((key, config[key]))

        return overrides

    def generate_config_label(
        self,
        job: Dict[str, Any],
        label_params: Optional[List[str]] = None,
        max_overrides: int = 3,
    ) -> str:
        """Generate human-readable label for a config."""
        config = job["config"]

        # Start with base config name
        base_name = config.get("run_name", config.get("config_name", "custom"))

        # Get overrides
        if label_params:
            # Show only requested params
            overrides = []
            for param in label_params:
                if "." in param:
                    # Handle nested params
                    parts = param.split(".")
                    val = config
                    try:
                        for part in parts:
                            val = val.get(part, {})
                        if val and val != {}:
                            overrides.append((param, val))
                    except:
                        pass
                elif param in config:
                    overrides.append((param, config[param]))
        else:
            # Auto-detect overrides
            overrides = self.detect_overrides(config)

        # Limit number of overrides shown
        if len(overrides) > max_overrides:
            overrides = overrides[:max_overrides]
            overrides.append(("...", ""))

        # Format label
        if overrides:
            override_strs = []
            for k, v in overrides:
                if k == "...":
                    override_strs.append("...")
                else:
                    # Shorten long values
                    if isinstance(v, float):
                        override_strs.append(f"{k}={v:.4g}")
                    elif isinstance(v, str) and len(v) > 10:
                        override_strs.append(f"{k}={v[:10]}...")
                    else:
                        override_strs.append(f"{k}={v}")

            return f"{base_name} ({', '.join(override_strs)})"

        return base_name

    def group_jobs_by_config(
        self, jobs: List[Dict[str, Any]], group_by: Optional[List[str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group jobs by their configuration (excluding seed)."""
        groups = defaultdict(list)

        if group_by:
            # Group by specific parameters only
            for job in jobs:
                # Extract specified params
                key_parts = []
                for param in group_by:
                    if "." in param:
                        parts = param.split(".")
                        val = job["config"]
                        try:
                            for part in parts:
                                val = val.get(part, "None")
                            key_parts.append(f"{param}={val}")
                        except:
                            key_parts.append(f"{param}=None")
                    else:
                        val = job["config"].get(param, "None")
                        key_parts.append(f"{param}={val}")

                key = "|".join(key_parts)
                groups[key].append(job)
        else:
            # Group by full config signature
            for job in jobs:
                sig = self.get_config_signature(job)
                groups[sig].append(job)

        return dict(groups)

    def filter_jobs(
        self, jobs: List[Dict[str, Any]], filters: List[str]
    ) -> List[Dict[str, Any]]:
        """Filter jobs by parameter values."""
        filtered = []

        for job in jobs:
            matches = True
            for filter_str in filters:
                if "=" in filter_str:
                    param, value = filter_str.split("=", 1)

                    # Handle nested params
                    if "." in param:
                        parts = param.split(".")
                        val = job["config"]
                        try:
                            for part in parts:
                                val = val.get(part)
                            if str(val) != value:
                                matches = False
                                break
                        except:
                            matches = False
                            break
                    else:
                        if str(job["config"].get(param)) != value:
                            matches = False
                            break
                else:
                    # Simple substring match in config
                    if filter_str not in str(job["config"]):
                        matches = False
                        break

            if matches:
                filtered.append(job)

        return filtered

    def extract_metrics(
        self, jobs: List[Dict[str, Any]], metric_names: List[str]
    ) -> Dict[str, Dict[str, np.ndarray]]:
        """Extract specified metrics from jobs."""
        metrics_data = defaultdict(lambda: defaultdict(list))

        for job in jobs:
            if "metrics_data" not in job:
                continue

            metrics = job["metrics_data"]
            epochs = sorted([int(e) for e in metrics.keys()])

            for epoch in epochs:
                epoch_data = metrics[str(epoch)]
                for metric_name in metric_names:
                    # First try direct match
                    if metric_name in epoch_data:
                        metrics_data[metric_name]["epochs"].append(epoch)
                        metrics_data[metric_name]["values"].append(
                            epoch_data[metric_name]
                        )
                    elif "/" in metric_name:
                        # Handle train/acc -> train_acc conversion
                        converted_name = metric_name.replace("/", "_")
                        if converted_name in epoch_data:
                            metrics_data[metric_name]["epochs"].append(epoch)
                            metrics_data[metric_name]["values"].append(
                                epoch_data[converted_name]
                            )
                        else:
                            # Try nested metrics (for backward compatibility)
                            parts = metric_name.split("/")
                            value = epoch_data
                            try:
                                for part in parts:
                                    value = value[part]
                                metrics_data[metric_name]["epochs"].append(epoch)
                                metrics_data[metric_name]["values"].append(value)
                            except (KeyError, TypeError):
                                pass

        # Convert to numpy arrays
        for metric_name in metrics_data:
            for key in ["epochs", "values"]:
                metrics_data[metric_name][key] = np.array(
                    metrics_data[metric_name][key]
                )

        return dict(metrics_data)

    def plot_metrics(
        self,
        grouped_jobs: Dict[str, List[Dict[str, Any]]],
        metric_names: List[str],
        log_epochs: bool = False,
        output_dir: Path = None,
        title: Optional[str] = None,
    ):
        """Plot metrics with mean and std across seeds."""
        if output_dir is None:
            output_dir = Path("./analysis_outputs")
        output_dir.mkdir(exist_ok=True)

        # Create a plot for each metric
        for metric_name in metric_names:
            fig, ax = plt.subplots(figsize=(10, 6))

            # Plot each config group
            for config_sig, jobs in grouped_jobs.items():
                # Get label for this config
                label = self.generate_config_label(jobs[0])

                # Extract metrics for all jobs in this group
                all_metrics = []
                epochs_list = []

                for job in jobs:
                    metrics = self.extract_metrics([job], [metric_name])
                    if metric_name in metrics:
                        all_metrics.append(metrics[metric_name]["values"])
                        epochs_list.append(metrics[metric_name]["epochs"])

                if not all_metrics:
                    print(f"Warning: No data found for {label} - {metric_name}")
                    continue

                # Find common epochs across all seeds
                common_epochs = epochs_list[0]
                for epochs in epochs_list[1:]:
                    common_epochs = np.intersect1d(common_epochs, epochs)

                if len(common_epochs) == 0:
                    print(f"Warning: No common epochs for {label}")
                    continue

                # Align all metrics to common epochs
                aligned_metrics = []
                for i, (epochs, values) in enumerate(zip(epochs_list, all_metrics)):
                    aligned_values = []
                    for epoch in common_epochs:
                        idx = np.where(epochs == epoch)[0][0]
                        aligned_values.append(values[idx])
                    aligned_metrics.append(aligned_values)

                # Calculate mean and std
                aligned_metrics = np.array(aligned_metrics)
                mean_values = np.mean(aligned_metrics, axis=0)
                std_values = np.std(aligned_metrics, axis=0)

                # Plot
                if log_epochs:
                    ax.semilogx(common_epochs, mean_values, label=label, linewidth=2)
                else:
                    ax.plot(common_epochs, mean_values, label=label, linewidth=2)

                # Add confidence interval
                ax.fill_between(
                    common_epochs,
                    mean_values - std_values,
                    mean_values + std_values,
                    alpha=0.3,
                )

            # Formatting
            ax.set_xlabel("Epochs (log scale)" if log_epochs else "Epochs")
            ax.set_ylabel(metric_name)
            ax.set_title(title or f"{metric_name} across configurations")
            ax.legend()
            ax.grid(True, alpha=0.3)

            # Save
            safe_metric_name = metric_name.replace("/", "_")
            filename = f"{safe_metric_name}{'_log' if log_epochs else ''}.png"
            filepath = output_dir / filename
            plt.savefig(filepath, dpi=300, bbox_inches="tight")
            print(f"Saved: {filepath}")

            plt.close()

    def list_configs(self, jobs: List[Dict[str, Any]]) -> None:
        """List all unique configurations with nice formatting."""
        grouped = self.group_jobs_by_config(jobs)

        print(f"\nFound {len(grouped)} unique configurations:\n")

        config_list = []
        for i, (sig, group_jobs) in enumerate(grouped.items()):
            label = self.generate_config_label(group_jobs[0])
            # Get the seeds for this config
            seeds = sorted([job["config"].get("seed", "?") for job in group_jobs])
            seed_str = f"seeds: {seeds}" if len(seeds) > 1 else f"seed: {seeds[0]}"
            config_list.append((i, sig, label, len(group_jobs), seed_str))

        # Sort by label for better readability
        config_list.sort(key=lambda x: x[2])

        for i, (_, sig, label, count, seed_str) in enumerate(config_list):
            print(f"{i:3d}. {label:<50} ({count} runs, {seed_str})")

        return {i: sig for i, sig, _, _, _ in config_list}


def main():
    parser = argparse.ArgumentParser(
        description="Analyze and plot metrics from completed experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all completed configurations
  %(prog)s --base-path ./exp --experiment test --list-configs
  
  # Plot specific metrics for all configs
  %(prog)s --base-path ./exp --experiment test --metrics val/acc train/loss
  
  # Plot with log scale epochs
  %(prog)s --base-path ./exp --experiment test --metrics val/acc --log-epochs
  
  # Filter to specific configs
  %(prog)s --base-path ./exp --experiment test --metrics val/acc \\
    --filter "run_name=step00_baseline" --filter "lr=0.1"
  
  # Plot specific configs by ID (after --list-configs)
  %(prog)s --base-path ./exp --experiment test --metrics val/acc \\
    --config-ids 0 2 5
  
  # Show specific parameters in labels
  %(prog)s --base-path ./exp --experiment test --metrics val/acc \\
    --label-params lr optimizer.weight_decay
  
  # Group by specific parameters only
  %(prog)s --base-path ./exp --experiment test --metrics val/acc \\
    --group-by run_name lr
""",
    )

    parser.add_argument(
        "--base-path", type=Path, default=Path.cwd(), help="Base path for experiments"
    )
    parser.add_argument("--experiment", required=True, help="Experiment name")
    parser.add_argument(
        "--metrics", nargs="+", help="Metrics to plot (e.g., val/acc train/loss)"
    )
    parser.add_argument(
        "--log-epochs", action="store_true", help="Use log scale for epochs"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for plots (default: ./analysis_outputs)",
    )
    parser.add_argument(
        "--list-configs",
        action="store_true",
        help="List all unique configurations and exit",
    )
    parser.add_argument(
        "--filter", action="append", default=[], help="Filter jobs by parameter=value"
    )
    parser.add_argument(
        "--config-ids",
        type=int,
        nargs="+",
        help="Plot specific config IDs (from --list-configs)",
    )
    parser.add_argument(
        "--label-params", nargs="+", help="Parameters to show in labels"
    )
    parser.add_argument(
        "--group-by", nargs="+", help="Group by specific parameters only"
    )
    parser.add_argument("--title", help="Plot title")

    args = parser.parse_args()

    # Initialize analyzer
    analyzer = MetricsAnalyzer(args.base_path, args.experiment)

    # Load completed jobs
    print("Loading completed jobs...")
    jobs = analyzer.load_completed_jobs()
    print(f"Found {len(jobs)} completed jobs")

    if not jobs:
        print("No completed jobs found!")
        return 1

    # Apply filters
    if args.filter:
        jobs = analyzer.filter_jobs(jobs, args.filter)
        print(f"After filtering: {len(jobs)} jobs")

    # Group jobs
    grouped = analyzer.group_jobs_by_config(jobs, args.group_by)

    # List configs mode
    if args.list_configs:
        config_map = analyzer.list_configs(jobs)
        return 0

    # Check if we need metrics
    if not args.metrics:
        print("\nError: Please specify metrics to plot with --metrics")
        print("Common metrics: val_acc train_acc val_loss train_loss")
        print(
            "Also supported: val/acc train/acc val/loss train/loss (converted automatically)"
        )
        return 1

    # Filter to specific config IDs if requested
    if args.config_ids is not None:
        # Need to get the config map
        temp_grouped = analyzer.group_jobs_by_config(jobs, args.group_by)
        config_list = []
        for sig, group_jobs in temp_grouped.items():
            config_list.append((sig, group_jobs))

        # Sort by label for consistent ordering
        config_list.sort(key=lambda x: analyzer.generate_config_label(x[1][0]))

        # Filter to selected IDs
        selected_grouped = {}
        for config_id in args.config_ids:
            if 0 <= config_id < len(config_list):
                sig, group_jobs = config_list[config_id]
                selected_grouped[sig] = group_jobs
            else:
                print(f"Warning: Config ID {config_id} out of range")

        if not selected_grouped:
            print("No valid config IDs selected!")
            return 1

        grouped = selected_grouped

    # Interactive selection if too many configs
    if len(grouped) > 10 and args.config_ids is None:
        print(f"\nFound {len(grouped)} configurations. Showing first 10:")
        config_list = []
        for i, (sig, group_jobs) in enumerate(list(grouped.items())[:10]):
            label = analyzer.generate_config_label(group_jobs[0])
            config_list.append((i, sig, label, len(group_jobs)))
            print(f"{i:3d}. {label:<50} ({len(group_jobs)} seeds)")

        print("\nToo many configs to plot. Please either:")
        print("1. Use --filter to narrow down")
        print("2. Use --config-ids to select specific ones")
        print("3. Use --group-by to merge similar configs")
        return 1

    # Plot metrics
    print(
        f"\nPlotting {len(args.metrics)} metrics for {len(grouped)} configurations..."
    )
    analyzer.plot_metrics(
        grouped,
        args.metrics,
        log_epochs=args.log_epochs,
        output_dir=args.output_dir,
        title=args.title,
    )

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
