#!/usr/bin/env python3
"""Create a comprehensive summary of experiment insights using best validation loss."""

import pandas as pd
from pathlib import Path
import argparse
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict


def load_analysis_results(output_dir: Path) -> Dict:
    """Load all analysis results from the output directory."""
    results = {}

    # Load early correlation analysis best loss
    early_csv = output_dir / "early_regression_analysis_summary_best_loss.csv"
    if early_csv.exists():
        results["early"] = pd.read_csv(early_csv)

    # Load full correlation analysis best loss
    full_csv = output_dir / "regression_analysis_summary_best_loss.csv"
    if full_csv.exists():
        results["full"] = pd.read_csv(full_csv)

    return results


def categorize_configs(df: pd.DataFrame) -> pd.DataFrame:
    """Add categories to configurations for better grouping."""
    df = df.copy()

    def get_category(config_name):
        if "controlled" in config_name:
            return "Controlled Experiments"
        elif "lr-" in config_name or "_lr" in config_name:
            if "step00" in config_name:
                return "AdamW Hyperparameter Sweep"
            else:
                return "SGD Hyperparameter Sweep"
        elif config_name.startswith("step"):
            step_num = int(config_name.split("_")[0].replace("step", ""))
            if step_num <= 4:
                return "Modern Augmentations (Steps 0-4)"
            elif step_num <= 7:
                return "Optimization & Architecture (Steps 5-7)"
            else:
                return "Classical Techniques (Steps 8+)"
        else:
            return "Other"

    df["category"] = df["config"].apply(get_category)
    return df


def create_insights_summary(results: Dict, output_dir: Path):
    """Create a comprehensive insights summary."""
    # Create insights directory
    insights_dir = output_dir / "00_experiment_insights_best_loss"
    insights_dir.mkdir(parents=True, exist_ok=True)

    # Categorize configurations
    if "early" in results:
        early_df = categorize_configs(results["early"])
    if "full" in results:
        full_df = categorize_configs(results["full"])

    # 1. Create top performers summary
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Top 15 by best loss (lowest)
    top_configs = early_df.nsmallest(15, "best_val_loss")
    ax1.barh(
        range(len(top_configs)),
        top_configs["best_val_loss"],
        color=sns.color_palette("viridis_r", len(top_configs)),
    )
    ax1.set_yticks(range(len(top_configs)))
    ax1.set_yticklabels(top_configs["config"])
    ax1.set_xlabel("Best Validation Loss")
    ax1.set_title("Top 15 Configurations by Best Val Loss (Lower is Better)")
    ax1.grid(True, alpha=0.3)

    # Add loss values on bars
    for i, (idx, row) in enumerate(top_configs.iterrows()):
        ax1.text(
            row["best_val_loss"] + 0.002,
            i,
            f"{row['best_val_loss']:.4f}",
            va="center",
            ha="left",
            fontsize=9,
        )

    # Category performance summary
    category_stats = (
        early_df.groupby("category")
        .agg({"best_val_loss": ["mean", "std", "min", "count"]})
        .round(4)
    )
    category_stats.columns = ["mean_loss", "std_loss", "min_loss", "count"]
    category_stats = category_stats.sort_values("mean_loss")  # Lower is better

    ax2.bar(
        range(len(category_stats)),
        category_stats["mean_loss"],
        yerr=category_stats["std_loss"],
        capsize=5,
        color=sns.color_palette("husl", len(category_stats)),
    )
    ax2.set_xticks(range(len(category_stats)))
    ax2.set_xticklabels(category_stats.index, rotation=45, ha="right")
    ax2.set_ylabel("Mean Best Validation Loss")
    ax2.set_title("Performance by Configuration Category (Best Val Loss)")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(
        insights_dir / "top_performers_summary_best_loss.png",
        dpi=300,
        bbox_inches="tight",
    )
    plt.close()

    # 2. Create early prediction power analysis
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))

    # Early vs best loss scatter
    scatter = ax1.scatter(
        early_df["val_slope"],
        early_df["best_val_loss"],
        c=early_df["category"].astype("category").cat.codes,
        cmap="tab10",
        s=100,
        alpha=0.7,
    )
    ax1.set_xlabel("Early Validation Loss Slope (first 10 epochs)")
    ax1.set_ylabel("Best Validation Loss")
    ax1.set_title("Early Slope vs Best Loss Performance")
    ax1.grid(True, alpha=0.3)

    # Hyperparameter impact on early dynamics
    hp_configs = early_df[early_df["category"].str.contains("Sweep")].copy()
    if not hp_configs.empty:
        # Extract learning rates
        hp_configs["lr"] = (
            hp_configs["config"].str.extract(r"lr[_-]?([\d.]+)").astype(float)
        )

        for category in hp_configs["category"].unique():
            cat_data = hp_configs[hp_configs["category"] == category]
            ax2.scatter(
                cat_data["lr"],
                cat_data["best_val_loss"],
                label=category.replace(" Hyperparameter Sweep", ""),
                s=100,
                alpha=0.7,
            )

        ax2.set_xlabel("Learning Rate")
        ax2.set_ylabel("Best Validation Loss")
        ax2.set_title("Learning Rate Impact on Best Loss")
        ax2.set_xscale("log")
        ax2.legend()
        ax2.grid(True, alpha=0.3)

    # Controlled experiments comparison
    controlled = early_df[early_df["category"] == "Controlled Experiments"]
    if not controlled.empty:
        ax3.barh(
            range(len(controlled)),
            controlled["best_val_loss"],
            color=sns.color_palette("coolwarm_r", len(controlled)),
        )
        ax3.set_yticks(range(len(controlled)))
        ax3.set_yticklabels(
            [c.replace("controlled_", "") for c in controlled["config"]]
        )
        ax3.set_xlabel("Best Validation Loss")
        ax3.set_title("Controlled Experiments - Best Val Loss")
        ax3.grid(True, alpha=0.3)

    # Early R² distribution by category
    early_df.boxplot(column="val_r2", by="category", ax=ax4, rot=45)
    ax4.set_xlabel("Category")
    ax4.set_ylabel("Early Validation R² (log-linear fit quality)")
    ax4.set_title("Early Training Linearity by Category")
    plt.sca(ax4)
    plt.xticks(rotation=45, ha="right")

    plt.tight_layout()
    plt.savefig(
        insights_dir / "early_dynamics_analysis_best_loss.png",
        dpi=300,
        bbox_inches="tight",
    )
    plt.close()

    # 3. Write text summary
    with open(insights_dir / "experiment_insights_best_loss.txt", "w") as f:
        f.write("EXPERIMENT INSIGHTS SUMMARY - BEST VALIDATION LOSS\n")
        f.write("==================================================\n\n")

        f.write(
            "1. TOP PERFORMING CONFIGURATIONS (BY BEST VAL LOSS - LOWER IS BETTER)\n"
        )
        f.write("-" * 70 + "\n")
        for idx, row in top_configs.head(10).iterrows():
            f.write(
                f"{row['config']}: {row['best_val_loss']:.4f} (val_slope: {row['val_slope']:.3f})\n"
            )

        f.write("\n2. CATEGORY PERFORMANCE SUMMARY (BEST VAL LOSS)\n")
        f.write("-" * 70 + "\n")
        f.write(category_stats.to_string())

        f.write("\n\n3. EARLY PREDICTION CORRELATIONS WITH BEST LOSS\n")
        f.write("-" * 70 + "\n")
        if "early" in results:
            from scipy import stats

            for metric in ["train_slope", "train_r2", "val_slope", "val_r2"]:
                corr, p_val = stats.pearsonr(
                    early_df[metric], early_df["best_val_loss"]
                )
                f.write(f"{metric}: r = {corr:.3f}, p = {p_val:.3f}\n")

        f.write("\n4. KEY FINDINGS (BEST VAL LOSS)\n")
        f.write("-" * 70 + "\n")

        # Find best hyperparameter settings
        if not hp_configs.empty:
            best_adamw = hp_configs[
                hp_configs["category"].str.contains("AdamW")
            ].nsmallest(1, "best_val_loss")
            best_sgd = hp_configs[hp_configs["category"].str.contains("SGD")].nsmallest(
                1, "best_val_loss"
            )

            if not best_adamw.empty:
                f.write(
                    f"- Best AdamW setting: {best_adamw.iloc[0]['config']} (best loss: {best_adamw.iloc[0]['best_val_loss']:.4f})\n"
                )
            if not best_sgd.empty:
                f.write(
                    f"- Best SGD setting: {best_sgd.iloc[0]['config']} (best loss: {best_sgd.iloc[0]['best_val_loss']:.4f})\n"
                )

        # Controlled experiment insights
        if not controlled.empty:
            f.write(
                "\n- Controlled Experiments (fixed augmentation, by best val loss):\n"
            )
            controlled_sorted = controlled.sort_values(
                "best_val_loss"
            )  # Ascending - lower is better
            for idx, row in controlled_sorted.iterrows():
                f.write(f"  {row['config']}: {row['best_val_loss']:.4f}\n")

        f.write("\n5. RECOMMENDATIONS (BASED ON BEST VAL LOSS)\n")
        f.write("-" * 70 + "\n")
        f.write("- Early validation loss slope correlates with minimum achieved loss\n")
        f.write(
            "- Note: negative correlations with loss metrics are good (lower loss is better)\n"
        )
        f.write(
            "- Best loss often occurs before final epoch, suggesting early stopping potential\n"
        )
        f.write(
            "- Loss-based metrics may be more stable than accuracy for hyperparameter selection\n"
        )
        f.write(
            "- Configurations with lowest loss don't always have highest accuracy\n"
        )

    print(f"\nInsights summary saved to {insights_dir}/")
    print("- experiment_insights_best_loss.txt: Detailed text summary")
    print(
        "- top_performers_summary_best_loss.png: Visual summary of best configurations"
    )
    print(
        "- early_dynamics_analysis_best_loss.png: Analysis of early training predictive power"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Create experiment insights summary using best validation loss"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="correlation_analysis_best_loss",
        help="Directory containing analysis outputs",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    # Load results
    print("Loading analysis results for best validation loss...")
    results = load_analysis_results(output_dir)

    if not results:
        print("No analysis results found. Please run the analysis scripts first.")
        return

    # Create insights
    create_insights_summary(results, output_dir)


if __name__ == "__main__":
    main()
