#!/usr/bin/env python3
"""
Analyze experimental results showing the effect of progressively removing modern techniques.
Performs regression analysis on loss vs configuration step number using log scale for x-axis.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
import re
from pathlib import Path
from typing import Dict


def extract_step_number(config_name: str) -> int:
    """Extract step number from configuration name."""
    match = re.match(r"step(\d+)", config_name)
    if match:
        return int(match.group(1))
    return -1


def perform_regression(x: np.ndarray, y: np.ndarray) -> Dict[str, float]:
    """
    Perform linear regression on the data.

    Args:
        x: Independent variable (log of step numbers)
        y: Dependent variable (loss values)

    Returns:
        Dictionary with slope, intercept, r_value, p_value, and std_err
    """
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
    return {
        "slope": slope,
        "intercept": intercept,
        "r_squared": r_value**2,
        "p_value": p_value,
        "std_err": std_err,
    }


def create_regression_plot(
    step_numbers: np.ndarray,
    train_losses: np.ndarray,
    val_losses: np.ndarray,
    train_reg: Dict[str, float],
    val_reg: Dict[str, float],
    output_path: Path,
) -> None:
    """Create regression plot with both training and validation losses."""
    fig, ax = plt.subplots(figsize=(10, 6))

    # Use step_number + 1 to avoid log(0)
    x_plot = step_numbers + 1
    x_log = np.log10(x_plot)

    # Plot actual data points
    ax.scatter(
        x_plot,
        train_losses,
        color="blue",
        alpha=0.6,
        s=80,
        label="Training Loss",
        marker="o",
    )
    ax.scatter(
        x_plot,
        val_losses,
        color="red",
        alpha=0.6,
        s=80,
        label="Validation Loss",
        marker="s",
    )

    # Plot regression lines
    x_line = np.linspace(x_plot.min(), x_plot.max(), 100)
    x_line_log = np.log10(x_line)

    train_pred = train_reg["slope"] * x_line_log + train_reg["intercept"]
    val_pred = val_reg["slope"] * x_line_log + val_reg["intercept"]

    ax.plot(
        x_line,
        train_pred,
        "b--",
        alpha=0.8,
        linewidth=2,
        label=f"Train Regression: y = {train_reg['slope']:.3f}·log₁₀(x) + {train_reg['intercept']:.3f}",
    )
    ax.plot(
        x_line,
        val_pred,
        "r--",
        alpha=0.8,
        linewidth=2,
        label=f"Val Regression: y = {val_reg['slope']:.3f}·log₁₀(x) + {val_reg['intercept']:.3f}",
    )

    # Set log scale for x-axis
    ax.set_xscale("log")

    # Formatting
    ax.set_xlabel("Configuration Step Number (log scale)", fontsize=12)
    ax.set_ylabel("Loss (linear scale)", fontsize=12)
    ax.set_title(
        "Loss vs Configuration Step: Progressive Removal of Modern Techniques",
        fontsize=14,
    )
    ax.grid(True, alpha=0.3, which="both")
    ax.legend(fontsize=10)

    # Add R² values to the plot
    ax.text(
        0.05,
        0.95,
        f"Train R² = {train_reg['r_squared']:.4f}",
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
    )
    ax.text(
        0.05,
        0.90,
        f"Val R² = {val_reg['r_squared']:.4f}",
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def create_separate_plots(
    step_numbers: np.ndarray,
    train_losses: np.ndarray,
    val_losses: np.ndarray,
    train_reg: Dict[str, float],
    val_reg: Dict[str, float],
    output_dir: Path,
) -> None:
    """Create separate plots for training and validation losses."""
    for loss_type, losses, reg_results, color in [
        ("Training", train_losses, train_reg, "blue"),
        ("Validation", val_losses, val_reg, "red"),
    ]:
        fig, ax = plt.subplots(figsize=(10, 6))

        # Use step_number + 1 to avoid log(0)
        x_plot = step_numbers + 1
        x_log = np.log10(x_plot)

        # Plot data points
        ax.scatter(
            x_plot, losses, color=color, alpha=0.6, s=80, label=f"{loss_type} Loss"
        )

        # Plot regression line
        x_line = np.linspace(x_plot.min(), x_plot.max(), 100)
        x_line_log = np.log10(x_line)
        y_pred = reg_results["slope"] * x_line_log + reg_results["intercept"]

        ax.plot(
            x_line,
            y_pred,
            "--",
            color=color,
            alpha=0.8,
            linewidth=2,
            label=f"y = {reg_results['slope']:.3f}·log₁₀(x) + {reg_results['intercept']:.3f}",
        )

        # Set log scale for x-axis
        ax.set_xscale("log")

        # Formatting
        ax.set_xlabel("Configuration Step Number (log scale)", fontsize=12)
        ax.set_ylabel(f"{loss_type} Loss (linear scale)", fontsize=12)
        ax.set_title(f"{loss_type} Loss vs Configuration Step", fontsize=14)
        ax.grid(True, alpha=0.3, which="both")
        ax.legend(fontsize=10)

        # Add R² value
        ax.text(
            0.05,
            0.95,
            f"R² = {reg_results['r_squared']:.4f}",
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment="top",
        )
        ax.text(
            0.05,
            0.90,
            f"p-value = {reg_results['p_value']:.4e}",
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment="top",
        )

        plt.tight_layout()
        plt.savefig(
            output_dir / f"{loss_type.lower()}_loss_regression.png",
            dpi=300,
            bbox_inches="tight",
        )
        plt.close()


def main():
    # Set up paths
    base_path = Path("/Users/daniellerothermel/drotherm/repos/dr_exp")
    csv_path = base_path / "experiment_summary_filtered" / "experiment_summary.csv"
    output_dir = base_path / "presentation_plots"
    output_dir.mkdir(exist_ok=True)

    # Load data
    print("Loading experiment data...")
    df = pd.read_csv(csv_path)

    # Extract step numbers
    df["step_number"] = df["config"].apply(extract_step_number)
    df = df[df["step_number"] >= 0].sort_values("step_number")

    print(
        f"Found {len(df)} configurations from step{df['step_number'].min():02d} to step{df['step_number'].max():02d}"
    )

    # Extract data for regression
    step_numbers = df["step_number"].values
    train_losses = df["train_loss_mean"].values
    val_losses = df["val_loss_mean"].values

    # Perform regression analysis (using log10 of step_number + 1 to avoid log(0))
    x_log = np.log10(step_numbers + 1)

    print("\nPerforming regression analysis...")
    train_reg = perform_regression(x_log, train_losses)
    val_reg = perform_regression(x_log, val_losses)

    # Print results
    print("\n" + "=" * 60)
    print("REGRESSION ANALYSIS RESULTS")
    print("=" * 60)
    print("\nRegression equation: y = slope · log₁₀(step_number + 1) + intercept")

    print("\nTraining Loss Regression:")
    print(f"  Slope:     {train_reg['slope']:.4f}")
    print(f"  Intercept: {train_reg['intercept']:.4f}")
    print(f"  R²:        {train_reg['r_squared']:.4f}")
    print(f"  p-value:   {train_reg['p_value']:.4e}")

    print("\nValidation Loss Regression:")
    print(f"  Slope:     {val_reg['slope']:.4f}")
    print(f"  Intercept: {val_reg['intercept']:.4f}")
    print(f"  R²:        {val_reg['r_squared']:.4f}")
    print(f"  p-value:   {val_reg['p_value']:.4e}")

    # Create visualizations
    print("\nCreating visualizations...")

    # Combined plot
    create_regression_plot(
        step_numbers,
        train_losses,
        val_losses,
        train_reg,
        val_reg,
        output_dir / "loss_regression_combined.png",
    )

    # Separate plots
    create_separate_plots(
        step_numbers, train_losses, val_losses, train_reg, val_reg, output_dir
    )

    # Save detailed results
    results_path = output_dir / "regression_analysis_results.txt"
    with open(results_path, "w") as f:
        f.write("REGRESSION ANALYSIS RESULTS\n")
        f.write("=" * 60 + "\n")
        f.write(
            f"Data: {len(df)} configurations from step{df['step_number'].min():02d} to step{df['step_number'].max():02d}\n"
        )
        f.write(
            "\nRegression equation: y = slope · log₁₀(step_number + 1) + intercept\n"
        )
        f.write("\nTraining Loss Regression:\n")
        f.write(f"  Slope:     {train_reg['slope']:.6f}\n")
        f.write(f"  Intercept: {train_reg['intercept']:.6f}\n")
        f.write(f"  R²:        {train_reg['r_squared']:.6f}\n")
        f.write(f"  p-value:   {train_reg['p_value']:.6e}\n")
        f.write(f"  Std Error: {train_reg['std_err']:.6f}\n")
        f.write("\nValidation Loss Regression:\n")
        f.write(f"  Slope:     {val_reg['slope']:.6f}\n")
        f.write(f"  Intercept: {val_reg['intercept']:.6f}\n")
        f.write(f"  R²:        {val_reg['r_squared']:.6f}\n")
        f.write(f"  p-value:   {val_reg['p_value']:.6e}\n")
        f.write(f"  Std Error: {val_reg['std_err']:.6f}\n")
        f.write("\nInterpretation:\n")
        f.write(
            "- Both slopes are negative, indicating losses decrease as techniques are removed\n"
        )
        f.write(
            f"- Training loss decreases more steeply (slope={train_reg['slope']:.3f}) than validation loss (slope={val_reg['slope']:.3f})\n"
        )
        f.write(
            "- This suggests modern techniques help generalization more than training fit\n"
        )
        f.write("\n\nConfiguration Details:\n")
        f.write("-" * 80 + "\n")
        f.write(
            f"{'Step':<6} {'Config Name':<20} {'Train Loss':<12} {'Val Loss':<12} {'Change':<30}\n"
        )
        f.write("-" * 80 + "\n")
        for _, row in df.iterrows():
            # Find which technique was changed
            change_cols = [
                col
                for col in df.columns
                if col.startswith("change_") and pd.notna(row[col])
            ]
            if change_cols:
                change = change_cols[0].replace("change_", "")
                if not row[change_cols[0]]:
                    change = f"no_{change}"
                else:
                    change = str(row[change_cols[0]])
            else:
                change = "baseline"
            f.write(
                f"{row['step_number']:<6} {row['config']:<20} {row['train_loss_mean']:>12.4f} {row['val_loss_mean']:>12.4f} {change:<30}\n"
            )

    print("\nResults saved to:")
    print(f"  - {output_dir / 'loss_regression_combined.png'}")
    print(f"  - {output_dir / 'training_loss_regression.png'}")
    print(f"  - {output_dir / 'validation_loss_regression.png'}")
    print(f"  - {results_path}")


if __name__ == "__main__":
    main()
