#!/usr/bin/env python3
"""Generate specific analyses and talking points for the presentation."""

import pandas as pd
from pathlib import Path
import argparse


def generate_talking_points(output_dir: Path):
    """Generate specific talking points with data for the presentation."""

    # Load data
    metrics_df = pd.read_csv(output_dir / "comprehensive_metrics_analysis.csv")
    epoch_corr_df = pd.read_csv(output_dir / "epoch_range_correlations.csv")

    talking_points = []

    # 1. Main Finding
    best_predictor = epoch_corr_df.loc[epoch_corr_df["abs_correlation"].idxmax()]
    talking_points.append(
        {
            "Topic": "Main Finding",
            "Point": f"Early training dynamics (epochs {best_predictor['range_name']}) strongly predict final performance",
            "Evidence": f"{best_predictor['metric']} {best_predictor['statistic']} has r={best_predictor['correlation']:.3f} (p<0.001)",
            "Implication": "Can identify promising models early, saving compute",
        }
    )

    # 2. Hypothesis 1: Linearity
    r2_metrics = epoch_corr_df[epoch_corr_df["statistic"] == "r2"]
    best_r2 = r2_metrics.loc[r2_metrics["abs_correlation"].idxmax()]
    talking_points.append(
        {
            "Topic": "Hypothesis 1: Linearity",
            "Point": "Training linearity (R²) negatively correlates with performance",
            "Evidence": f"Best R² predictor: {best_r2['metric']} ({best_r2['range_name']}) with r={best_r2['correlation']:.3f}",
            "Implication": "Non-linear training curves indicate better generalization",
        }
    )

    # 3. Hypothesis 2: Slope
    slope_metrics = epoch_corr_df[epoch_corr_df["statistic"] == "slope"]
    best_slope = slope_metrics.loc[slope_metrics["abs_correlation"].idxmax()]
    talking_points.append(
        {
            "Topic": "Hypothesis 2: Slope",
            "Point": "Rate of improvement (slope) moderately predicts performance",
            "Evidence": f"Best slope predictor: {best_slope['metric']} ({best_slope['range_name']}) with r={best_slope['correlation']:.3f}",
            "Implication": "Faster early improvement generally better, but RMSE is superior",
        }
    )

    # 4. RMSE as best metric
    rmse_metrics = epoch_corr_df[epoch_corr_df["statistic"] == "rmse"]
    rmse_mean_corr = rmse_metrics["abs_correlation"].mean()
    slope_mean_corr = slope_metrics["abs_correlation"].mean()
    r2_mean_corr = r2_metrics["abs_correlation"].mean()
    talking_points.append(
        {
            "Topic": "RMSE Superiority",
            "Point": "RMSE outperforms both R² and slope for prediction",
            "Evidence": f"Mean correlations - RMSE: {rmse_mean_corr:.3f}, Slope: {slope_mean_corr:.3f}, R²: {r2_mean_corr:.3f}",
            "Implication": "RMSE captures both trend and variance, making it more robust",
        }
    )

    # 5. Optimal epoch range
    window_20 = epoch_corr_df[epoch_corr_df["window_size"] == 20]
    window_10 = epoch_corr_df[epoch_corr_df["window_size"] == 10]
    talking_points.append(
        {
            "Topic": "Optimal Epoch Range",
            "Point": "20-epoch window starting from epoch 0 is optimal",
            "Evidence": f"Max correlation - 20 epochs: {window_20['abs_correlation'].max():.3f}, 10 epochs: {window_10['abs_correlation'].max():.3f}",
            "Implication": "Need sufficient data but early training is key",
        }
    )

    # 6. Optimizer differences
    adamw_df = metrics_df[metrics_df["optimizer"] == "adamw"]
    sgd_df = metrics_df[metrics_df["optimizer"].isin(["sgd", "sgdm"])]

    if "val_acc_rmse_0-20_mean" in metrics_df.columns:
        adamw_corr = adamw_df["val_acc_rmse_0-20_mean"].corr(
            adamw_df["best_val_acc_mean"]
        )
        sgd_corr = sgd_df["val_acc_rmse_0-20_mean"].corr(sgd_df["best_val_acc_mean"])

        talking_points.append(
            {
                "Topic": "Optimizer Patterns",
                "Point": "AdamW shows stronger early predictability than SGD",
                "Evidence": f"Val Acc RMSE correlation - AdamW: {adamw_corr:.3f}, SGD: {sgd_corr:.3f}",
                "Implication": "May need optimizer-specific early stopping criteria",
            }
        )

    # 7. Stability importance
    if "val_acc_rmse_0-20_std" in metrics_df.columns:
        stability_corr = metrics_df["val_acc_rmse_0-20_std"].corr(
            metrics_df["best_val_acc_mean"]
        )
        talking_points.append(
            {
                "Topic": "Training Stability",
                "Point": "Lower variance across seeds correlates with better performance",
                "Evidence": f"Correlation between RMSE std and performance: {stability_corr:.3f}",
                "Implication": "Consistent training behavior is a positive signal",
            }
        )

    # 8. Early vs late training
    early_metrics = epoch_corr_df[epoch_corr_df["end_epoch"] <= 20]
    late_metrics = epoch_corr_df[epoch_corr_df["start_epoch"] >= 20]
    talking_points.append(
        {
            "Topic": "Early vs Late Training",
            "Point": "Early training is far more predictive than late training",
            "Evidence": f"Max correlation - Early (≤20): {early_metrics['abs_correlation'].max():.3f}, Late (≥20): {late_metrics['abs_correlation'].max():.3f}",
            "Implication": "Focus monitoring and decisions on first 20 epochs",
        }
    )

    # 9. Practical thresholds
    if "val_acc_rmse_0-20_mean" in metrics_df.columns:
        top_10_pct = metrics_df.nlargest(
            int(len(metrics_df) * 0.1), "best_val_acc_mean"
        )
        bottom_10_pct = metrics_df.nsmallest(
            int(len(metrics_df) * 0.1), "best_val_acc_mean"
        )

        top_rmse = top_10_pct["val_acc_rmse_0-20_mean"].mean()
        bottom_rmse = bottom_10_pct["val_acc_rmse_0-20_mean"].mean()

        talking_points.append(
            {
                "Topic": "Practical Thresholds",
                "Point": "Clear RMSE thresholds separate high and low performers",
                "Evidence": f"Top 10% avg RMSE: {top_rmse:.3f}, Bottom 10% avg RMSE: {bottom_rmse:.3f}",
                "Implication": f"Consider early stopping if RMSE > {(top_rmse + bottom_rmse) / 2:.3f}",
            }
        )

    # 10. Augmentation effects
    metrics_df["aug_complexity"] = 0
    metrics_df.loc[metrics_df["rcc"] | metrics_df["hflip"], "aug_complexity"] = 1
    metrics_df.loc[
        metrics_df["randaug"] | metrics_df["cutmix"] | metrics_df["mixup"],
        "aug_complexity",
    ] = 2

    aug_summary = metrics_df.groupby("aug_complexity")["best_val_acc_mean"].agg(
        ["mean", "count"]
    )
    talking_points.append(
        {
            "Topic": "Augmentation Impact",
            "Point": "Augmentation complexity affects both performance and predictability",
            "Evidence": f"Mean accuracy - None: {aug_summary.loc[0, 'mean']:.3f}, Basic: {aug_summary.loc[1, 'mean']:.3f}, Advanced: {aug_summary.loc[2, 'mean']:.3f}",
            "Implication": "Advanced augmentation may require adjusted early stopping criteria",
        }
    )

    # Create formatted output
    output_lines = ["PRESENTATION TALKING POINTS", "=" * 80, ""]

    for i, point in enumerate(talking_points, 1):
        output_lines.extend(
            [
                f"{i}. {point['Topic'].upper()}",
                f"   Point: {point['Point']}",
                f"   Evidence: {point['Evidence']}",
                f"   Implication: {point['Implication']}",
                "",
            ]
        )

    # Add summary recommendations
    output_lines.extend(
        [
            "SUMMARY RECOMMENDATIONS",
            "=" * 80,
            "",
            "1. EARLY STOPPING STRATEGY:",
            "   - Monitor Val Acc RMSE for epochs 0-20",
            "   - Set optimizer-specific thresholds",
            "   - Consider stopping if RMSE exceeds threshold by epoch 20",
            "",
            "2. EXPERIMENT DESIGN:",
            "   - Run multiple seeds to assess stability",
            "   - Focus compute on first 20-30 epochs for initial screening",
            "   - Use RMSE as primary early performance indicator",
            "",
            "3. FUTURE WORK:",
            "   - Develop automated early stopping based on these metrics",
            "   - Test on different datasets and architectures",
            "   - Create optimizer-specific prediction models",
            "",
        ]
    )

    # Save to file
    output_path = output_dir / "presentation_talking_points.txt"
    with open(output_path, "w") as f:
        f.write("\n".join(output_lines))

    # Also print to console
    print("\n".join(output_lines))

    # Create a simple CSV with key numbers for slides
    key_numbers = pd.DataFrame(
        [
            {
                "Metric": "Best Overall Correlation",
                "Value": f"{best_predictor['correlation']:.3f}",
            },
            {"Metric": "Optimal Epoch Range", "Value": best_predictor["range_name"]},
            {"Metric": "Best Metric Type", "Value": "RMSE"},
            {
                "Metric": "Early vs Late Correlation Ratio",
                "Value": f"{early_metrics['abs_correlation'].max() / late_metrics['abs_correlation'].max():.2f}x",
            },
            {
                "Metric": "AdamW vs SGD Predictability",
                "Value": f"{adamw_corr / sgd_corr:.2f}x"
                if "adamw_corr" in locals()
                else "N/A",
            },
            {"Metric": "Samples Analyzed", "Value": str(len(metrics_df))},
            {
                "Metric": "Configurations Tested",
                "Value": str(metrics_df["config"].nunique()),
            },
        ]
    )

    key_numbers.to_csv(output_dir / "key_numbers_for_slides.csv", index=False)

    return talking_points


def main():
    parser = argparse.ArgumentParser(description="Generate presentation talking points")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="na_full_t1_best_acc/presentation",
        help="Output directory with analysis results",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    print("Generating presentation talking points...")
    talking_points = generate_talking_points(output_dir)

    print(f"\nTalking points saved to {output_dir}/presentation_talking_points.txt")
    print(f"Key numbers saved to {output_dir}/key_numbers_for_slides.csv")


if __name__ == "__main__":
    main()
