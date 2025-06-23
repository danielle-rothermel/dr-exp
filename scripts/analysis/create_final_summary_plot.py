#!/usr/bin/env python3
"""Create final summary plot showing key findings from the regression analysis."""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


def main():
    """Create final summary visualization."""
    output_dir = Path(
        "/Users/daniellerothermel/drotherm/repos/dr_exp/presentation_plots"
    )

    # Read regression results
    results_df = pd.read_csv(output_dir / "regression_analysis_results.csv")

    # Create figure with subplots
    fig = plt.figure(figsize=(16, 10))

    # 1. Bar chart of slopes
    ax1 = plt.subplot(2, 2, 1)
    configs = results_df["config"].values
    slopes = results_df["slope"].values
    colors = ["red" if s > -0.1 else "orange" if s > -0.5 else "blue" for s in slopes]

    bars = ax1.barh(range(len(configs)), slopes, color=colors, alpha=0.7)
    ax1.set_yticks(range(len(configs)))
    ax1.set_yticklabels(configs, fontsize=9)
    ax1.set_xlabel("Regression Slope (more negative = faster learning)", fontsize=11)
    ax1.set_title("A. Learning Rate in Log-Epoch Space", fontsize=12, fontweight="bold")
    ax1.grid(True, axis="x", alpha=0.3)
    ax1.axvline(x=0, color="black", linewidth=1)

    # Add value labels
    for i, (bar, slope) in enumerate(zip(bars, slopes)):
        ax1.text(
            slope + 0.01 if slope < 0 else slope - 0.01,
            i,
            f"{slope:.3f}",
            va="center",
            ha="left" if slope < 0 else "right",
            fontsize=8,
        )

    # 2. Scatter plot: Slope vs Final Loss
    ax2 = plt.subplot(2, 2, 2)
    scatter = ax2.scatter(
        slopes,
        results_df["final_loss"],
        c=results_df["r_squared"],
        s=100,
        cmap="viridis",
        alpha=0.7,
        edgecolors="black",
    )

    # Add labels for interesting points
    for i, config in enumerate(configs):
        if config in [
            "step00_baseline",
            "step10_no_lrn",
            "step16_no_rrc",
            "step06_steplr",
            "step07_no_residual",
        ]:
            ax2.annotate(
                config,
                (slopes[i], results_df["final_loss"].iloc[i]),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=8,
            )

    ax2.set_xlabel("Regression Slope", fontsize=11)
    ax2.set_ylabel("Final Training Loss", fontsize=11)
    ax2.set_title("B. Learning Rate vs Final Loss", fontsize=12, fontweight="bold")
    ax2.grid(True, alpha=0.3)

    cbar = plt.colorbar(scatter, ax=ax2)
    cbar.set_label("R² Value", fontsize=10)

    # 3. Grouped bar chart by configuration type
    ax3 = plt.subplot(2, 2, 3)

    # Define groups
    groups = {
        "Baseline": ["step00_baseline"],
        "Optimizer": ["step01_sgd", "step05_no_warmup", "step06_steplr"],
        "Data Aug": [
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

    group_means = {}
    group_stds = {}
    for group_name, group_configs in groups.items():
        group_slopes = [slopes[i] for i, c in enumerate(configs) if c in group_configs]
        group_means[group_name] = np.mean(group_slopes)
        group_stds[group_name] = np.std(group_slopes)

    x_pos = np.arange(len(groups))
    bars = ax3.bar(
        x_pos,
        list(group_means.values()),
        yerr=list(group_stds.values()),
        capsize=5,
        alpha=0.7,
        color=["green", "blue", "orange", "red"],
    )

    ax3.set_xticks(x_pos)
    ax3.set_xticklabels(list(groups.keys()))
    ax3.set_ylabel("Mean Regression Slope", fontsize=11)
    ax3.set_title(
        "C. Average Learning Rate by Configuration Type", fontsize=12, fontweight="bold"
    )
    ax3.grid(True, axis="y", alpha=0.3)

    # Add value labels
    for bar, mean in zip(bars, group_means.values()):
        ax3.text(
            bar.get_x() + bar.get_width() / 2,
            mean - 0.02,
            f"{mean:.3f}",
            ha="center",
            va="top",
            fontsize=9,
        )

    # 4. Key findings text
    ax4 = plt.subplot(2, 2, 4)
    ax4.axis("off")

    findings_text = """Key Findings from Regression Analysis:

1. Architecture Changes Show Minimal Learning:
   • step10_no_lrn, step09_xavier, step08_lrn_dropout
   • Slopes ≈ -0.001 (essentially flat in log space)
   • These configurations failed to learn effectively

2. Data Augmentation Removals Improve Learning:
   • Removing augmentations (especially no_hflip, no_rrc)
   • Results in steeper negative slopes (-0.83 to -0.85)
   • Suggests simpler training dynamics

3. Optimizer Changes Have Moderate Impact:
   • StepLR scheduler (slope = -0.57) improves over baseline
   • SGD performs similarly to baseline AdamW

4. Model Architecture Matters:
   • Removing residual connections improves learning
   • AlexNet and ResNet12 show good learning rates
   • Certain architectural choices prevent learning entirely

Regression Model: loss = slope × log₁₀(epoch) + intercept"""

    ax4.text(
        0.05,
        0.95,
        findings_text,
        transform=ax4.transAxes,
        fontsize=11,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.3),
    )

    plt.suptitle(
        "Training Loss Regression Analysis Summary", fontsize=16, fontweight="bold"
    )
    plt.tight_layout()
    plt.savefig(
        output_dir / "regression_analysis_summary.png", dpi=300, bbox_inches="tight"
    )
    plt.close()

    # Create a simple table of top/bottom performers
    fig2, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Top 5 fastest learners
    top5 = results_df.nsmallest(5, "slope")[
        ["config", "slope", "final_loss", "r_squared"]
    ]
    # Format the data for the table
    top5_data = []
    for _, row in top5.iterrows():
        top5_data.append(
            [
                row["config"],
                f"{row['slope']:.3f}",
                f"{row['final_loss']:.3f}",
                f"{row['r_squared']:.3f}",
            ]
        )

    ax1.axis("tight")
    ax1.axis("off")
    table1 = ax1.table(
        cellText=top5_data,
        colLabels=["Configuration", "Slope", "Final Loss", "R²"],
        cellLoc="center",
        loc="center",
    )
    table1.auto_set_font_size(False)
    table1.set_fontsize(10)
    table1.scale(1.2, 1.5)
    ax1.set_title(
        "Top 5 Fastest Learning Configurations", fontsize=14, fontweight="bold", pad=20
    )

    # Bottom 5 slowest learners
    bottom5 = results_df.nlargest(5, "slope")[
        ["config", "slope", "final_loss", "r_squared"]
    ]
    # Format the data for the table
    bottom5_data = []
    for _, row in bottom5.iterrows():
        bottom5_data.append(
            [
                row["config"],
                f"{row['slope']:.3f}",
                f"{row['final_loss']:.3f}",
                f"{row['r_squared']:.3f}",
            ]
        )

    ax2.axis("tight")
    ax2.axis("off")
    table2 = ax2.table(
        cellText=bottom5_data,
        colLabels=["Configuration", "Slope", "Final Loss", "R²"],
        cellLoc="center",
        loc="center",
    )
    table2.auto_set_font_size(False)
    table2.set_fontsize(10)
    table2.scale(1.2, 1.5)
    ax2.set_title(
        "Bottom 5 Slowest Learning Configurations",
        fontsize=14,
        fontweight="bold",
        pad=20,
    )

    plt.suptitle(
        "Best and Worst Performing Configurations", fontsize=16, fontweight="bold"
    )
    plt.tight_layout()
    plt.savefig(output_dir / "top_bottom_performers.png", dpi=300, bbox_inches="tight")
    plt.close()

    print(f"\nSummary plots saved to: {output_dir}")


if __name__ == "__main__":
    main()
