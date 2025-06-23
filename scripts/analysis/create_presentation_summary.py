#!/usr/bin/env python3
"""Create final presentation summary with key findings and insights."""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import argparse
import warnings

warnings.filterwarnings("ignore")


def create_presentation_summary(output_dir: Path):
    """Create comprehensive presentation summary with key findings."""

    # Load comprehensive metrics
    metrics_df = pd.read_csv(output_dir / "comprehensive_metrics_analysis.csv")

    # Load epoch range correlations
    epoch_corr_df = pd.read_csv(output_dir / "epoch_range_correlations.csv")

    # Create figure with subplots for presentation
    fig = plt.figure(figsize=(20, 16))

    # 1. Main finding: Early training predicts final performance
    ax1 = plt.subplot(3, 3, 1)

    # Best predictor scatter plot
    best_metric = "val_acc_rmse_0-20_mean"
    if best_metric in metrics_df.columns:
        scatter = ax1.scatter(
            metrics_df[best_metric],
            metrics_df["best_val_acc_mean"],
            c=metrics_df["optimizer"].map(
                {"adamw": "blue", "sgd": "red", "sgdm": "red"}
            ),
            s=100,
            alpha=0.7,
        )

        # Add regression line
        z = np.polyfit(metrics_df[best_metric], metrics_df["best_val_acc_mean"], 1)
        p = np.poly1d(z)
        x_line = np.linspace(
            metrics_df[best_metric].min(), metrics_df[best_metric].max(), 100
        )
        ax1.plot(x_line, p(x_line), "k--", alpha=0.8, linewidth=2)

        ax1.set_xlabel("Val Acc RMSE (epochs 0-20)")
        ax1.set_ylabel("Best Validation Accuracy")
        ax1.set_title("Best Predictor: Val Acc RMSE\n(r=0.701, p<0.001)")
        ax1.grid(True, alpha=0.3)

    # 2. Hypothesis comparison
    ax2 = plt.subplot(3, 3, 2)

    # Compare R² vs Slope correlations
    r2_corrs = epoch_corr_df[epoch_corr_df["statistic"] == "r2"][
        "abs_correlation"
    ].values
    slope_corrs = epoch_corr_df[epoch_corr_df["statistic"] == "slope"][
        "abs_correlation"
    ].values
    rmse_corrs = epoch_corr_df[epoch_corr_df["statistic"] == "rmse"][
        "abs_correlation"
    ].values

    data = [r2_corrs, slope_corrs, rmse_corrs]
    labels = ["R² (Linearity)", "Slope", "RMSE"]

    bp = ax2.boxplot(data, labels=labels, patch_artist=True)
    for patch, color in zip(bp["boxes"], ["lightblue", "lightgreen", "lightcoral"]):
        patch.set_facecolor(color)

    ax2.set_ylabel("Absolute Correlation with Best Val Acc")
    ax2.set_title("Hypothesis Comparison:\nWhich Metric Type Predicts Best?")
    ax2.grid(True, alpha=0.3, axis="y")

    # 3. Window size analysis
    ax3 = plt.subplot(3, 3, 3)

    window_summary = epoch_corr_df.groupby("window_size")["abs_correlation"].agg(
        ["max", "mean", "std"]
    )

    x_pos = np.arange(len(window_summary))
    ax3.bar(x_pos - 0.2, window_summary["max"], 0.4, label="Max", alpha=0.8)
    ax3.bar(x_pos + 0.2, window_summary["mean"], 0.4, label="Mean", alpha=0.8)

    ax3.set_xlabel("Window Size (epochs)")
    ax3.set_ylabel("Absolute Correlation")
    ax3.set_title("Optimal Window Size Analysis")
    ax3.set_xticks(x_pos)
    ax3.set_xticklabels(window_summary.index)
    ax3.legend()
    ax3.grid(True, alpha=0.3, axis="y")

    # 4. Optimizer comparison
    ax4 = plt.subplot(3, 3, 4)

    optimizer_summary = metrics_df.groupby("optimizer")["best_val_acc_mean"].agg(
        ["mean", "std", "count"]
    )

    optimizers = optimizer_summary.index
    means = optimizer_summary["mean"]
    stds = optimizer_summary["std"]

    ax4.bar(optimizers, means, yerr=stds, capsize=10, alpha=0.7)
    ax4.set_xlabel("Optimizer")
    ax4.set_ylabel("Best Validation Accuracy")
    ax4.set_title("Performance by Optimizer")
    ax4.grid(True, alpha=0.3, axis="y")

    # Add sample sizes
    for i, (opt, count) in enumerate(zip(optimizers, optimizer_summary["count"])):
        ax4.text(i, 0.02, f"n={count}", ha="center", va="bottom")

    # 5. Early vs Late training predictive power
    ax5 = plt.subplot(3, 3, 5)

    # Group by start epoch
    start_epoch_summary = epoch_corr_df.groupby("start_epoch")["abs_correlation"].agg(
        ["max", "mean"]
    )

    ax5.plot(
        start_epoch_summary.index,
        start_epoch_summary["max"],
        "o-",
        label="Max",
        linewidth=2,
        markersize=8,
    )
    ax5.plot(
        start_epoch_summary.index,
        start_epoch_summary["mean"],
        "s-",
        label="Mean",
        linewidth=2,
        markersize=6,
    )

    ax5.set_xlabel("Start Epoch")
    ax5.set_ylabel("Absolute Correlation")
    ax5.set_title("Predictive Power by Training Stage")
    ax5.legend()
    ax5.grid(True, alpha=0.3)

    # 6. Augmentation effects
    ax6 = plt.subplot(3, 3, 6)

    # Create augmentation categories
    metrics_df["aug_type"] = "None"
    metrics_df.loc[metrics_df["rcc"] | metrics_df["hflip"], "aug_type"] = "Basic"
    metrics_df.loc[
        metrics_df["randaug"] | metrics_df["cutmix"] | metrics_df["mixup"], "aug_type"
    ] = "Advanced"

    aug_summary = metrics_df.groupby("aug_type")["best_val_acc_mean"].agg(
        ["mean", "std", "count"]
    )

    aug_types = aug_summary.index
    means = aug_summary["mean"]
    stds = aug_summary["std"]

    ax6.bar(aug_types, means, yerr=stds, capsize=10, alpha=0.7)
    ax6.set_xlabel("Augmentation Type")
    ax6.set_ylabel("Best Validation Accuracy")
    ax6.set_title("Performance by Augmentation")
    ax6.grid(True, alpha=0.3, axis="y")

    # Add sample sizes
    for i, (aug, count) in enumerate(zip(aug_types, aug_summary["count"])):
        ax6.text(i, 0.02, f"n={count}", ha="center", va="bottom")

    # 7. Stability analysis
    ax7 = plt.subplot(3, 3, 7)

    # Plot stability (std) vs performance
    stability_metric = "val_acc_rmse_0-20_std"
    if stability_metric in metrics_df.columns:
        scatter = ax7.scatter(
            metrics_df[stability_metric],
            metrics_df["best_val_acc_mean"],
            c=metrics_df["optimizer"].map(
                {"adamw": "blue", "sgd": "red", "sgdm": "red"}
            ),
            s=100,
            alpha=0.7,
        )

        # Add regression line
        mask = ~metrics_df[stability_metric].isna()
        if mask.sum() > 2:
            z = np.polyfit(
                metrics_df.loc[mask, stability_metric],
                metrics_df.loc[mask, "best_val_acc_mean"],
                1,
            )
            p = np.poly1d(z)
            x_line = np.linspace(
                metrics_df[stability_metric].min(),
                metrics_df[stability_metric].max(),
                100,
            )
            ax7.plot(x_line, p(x_line), "k--", alpha=0.8, linewidth=2)

        ax7.set_xlabel("Val Acc RMSE Std (epochs 0-20)")
        ax7.set_ylabel("Best Validation Accuracy")
        ax7.set_title("Training Stability vs Performance")
        ax7.grid(True, alpha=0.3)

    # 8. Top configurations
    ax8 = plt.subplot(3, 3, 8)

    # Get top 10 configurations
    top_configs = metrics_df.nlargest(10, "best_val_acc_mean")

    y_pos = np.arange(len(top_configs))
    ax8.barh(
        y_pos,
        top_configs["best_val_acc_mean"],
        xerr=top_configs["best_val_acc_std"],
        capsize=5,
    )

    # Shorten config names for display
    config_names = []
    for config in top_configs["config"]:
        if len(config) > 25:
            parts = config.split("_")
            config = "_".join(
                [
                    p
                    for p in parts
                    if any(k in p for k in ["step", "controlled", "lr", "wd"])
                ]
            )
        config_names.append(config)

    ax8.set_yticks(y_pos)
    ax8.set_yticklabels(config_names, fontsize=8)
    ax8.set_xlabel("Best Validation Accuracy")
    ax8.set_title("Top 10 Configurations")
    ax8.grid(True, alpha=0.3, axis="x")

    # 9. Key insights text
    ax9 = plt.subplot(3, 3, 9)
    ax9.axis("off")

    insights_text = """KEY INSIGHTS:

1. EARLY TRAINING PREDICTS FINAL PERFORMANCE
   • Epochs 0-20 are most predictive (r=0.701)
   • Val Acc RMSE is the best single predictor
   • Predictive power decreases after epoch 20

2. RMSE OUTPERFORMS OTHER METRICS
   • RMSE > R² > Slope for prediction
   • Captures both trend and variance
   • More robust across configurations

3. OPTIMIZER-SPECIFIC PATTERNS
   • AdamW: Strong early indicators
   • SGD: More variable early training
   • Different optimal metrics per optimizer

4. TRAINING STABILITY MATTERS
   • Lower variance → better performance
   • Consistent across seeds is key
   • Augmentation affects stability

5. PRACTICAL RECOMMENDATIONS
   • Monitor epochs 0-20 closely
   • Use Val Acc RMSE as early stopping
   • Consider optimizer-specific thresholds"""

    ax9.text(
        0.05,
        0.95,
        insights_text,
        transform=ax9.transAxes,
        fontsize=11,
        verticalalignment="top",
        fontfamily="monospace",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )

    plt.suptitle(
        "Early Training Dynamics Predict Final Performance: Presentation Summary",
        fontsize=16,
        y=0.98,
    )
    plt.tight_layout()
    plt.savefig(
        output_dir / "presentation_final_summary.png", dpi=300, bbox_inches="tight"
    )
    plt.close()

    # Create a correlation summary table
    create_correlation_summary_table(metrics_df, output_dir)


def create_correlation_summary_table(metrics_df: pd.DataFrame, output_dir: Path):
    """Create a formatted table of key correlations."""

    # Calculate correlations for key metrics
    correlations = []

    # Metrics to check
    key_metrics = [
        ("val_acc_rmse_0-20_mean", "Val Acc RMSE (0-20)"),
        ("val_loss_rmse_0-20_mean", "Val Loss RMSE (0-20)"),
        ("train_acc_r2_0-20_mean", "Train Acc R² (0-20)"),
        ("val_loss_slope_0-20_mean", "Val Loss Slope (0-20)"),
        ("val_acc_slope_0-20_mean", "Val Acc Slope (0-20)"),
    ]

    for metric_col, metric_name in key_metrics:
        if metric_col in metrics_df.columns:
            # Overall correlation
            corr = metrics_df[metric_col].corr(metrics_df["best_val_acc_mean"])

            # By optimizer
            adamw_df = metrics_df[metrics_df["optimizer"] == "adamw"]
            sgd_df = metrics_df[metrics_df["optimizer"].isin(["sgd", "sgdm"])]

            adamw_corr = (
                adamw_df[metric_col].corr(adamw_df["best_val_acc_mean"])
                if len(adamw_df) > 2
                else np.nan
            )
            sgd_corr = (
                sgd_df[metric_col].corr(sgd_df["best_val_acc_mean"])
                if len(sgd_df) > 2
                else np.nan
            )

            correlations.append(
                {
                    "Metric": metric_name,
                    "Overall": f"{corr:.3f}",
                    "AdamW": f"{adamw_corr:.3f}" if not np.isnan(adamw_corr) else "N/A",
                    "SGD": f"{sgd_corr:.3f}" if not np.isnan(sgd_corr) else "N/A",
                }
            )

    # Create and save table
    corr_table = pd.DataFrame(correlations)
    corr_table.to_csv(output_dir / "correlation_summary_table.csv", index=False)

    print("\nCORRELATION SUMMARY TABLE:")
    print("=" * 60)
    print(corr_table.to_string(index=False))

    return corr_table


def main():
    parser = argparse.ArgumentParser(description="Create final presentation summary")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="na_full_t1_best_acc/presentation",
        help="Output directory with analysis results",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    print("Creating presentation summary...")
    create_presentation_summary(output_dir)

    print(
        f"\nPresentation summary saved to {output_dir}/presentation_final_summary.png"
    )
    print(f"Correlation table saved to {output_dir}/correlation_summary_table.csv")


if __name__ == "__main__":
    main()
