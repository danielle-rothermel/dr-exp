#!/bin/bash
# Run all regression analyses for an experiment (v2 - handles hyperparameter variations)

# Default values
BASE_PATH="."
EXPERIMENT="cluster_t0"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --base-path)
            BASE_PATH="$2"
            shift 2
            ;;
        --experiment)
            EXPERIMENT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--base-path PATH] [--experiment NAME]"
            exit 1
            ;;
    esac
done

echo "Running all analyses for experiment: $EXPERIMENT (v2 - with hyperparameter handling)"
echo "Base path: $BASE_PATH"
echo ""

# Create output directory
OUTPUT_DIR="na_full_t1"
mkdir -p "$OUTPUT_DIR"

# 1. Create line plots
echo "1. Creating line plots..."
uv run python scripts/create_line_plots.py \
    --base-path "$BASE_PATH" \
    --experiment "$EXPERIMENT" \
    --output-dir "$OUTPUT_DIR/01_line_plots"

# 2. Create training loss regression plots
echo -e "\n2. Creating training loss regression plots..."
uv run python scripts/create_training_loss_regression_plots.py \
    --base-path "$BASE_PATH" \
    --experiment "$EXPERIMENT" \
    --output-dir "$OUTPUT_DIR/02_regression_plots"

# 3. Analyze training loss correlations (original version)
echo -e "\n3a. Analyzing training loss correlations (original grouping)..."
uv run python scripts/analyze_regression_correlations.py \
    --base-path "$BASE_PATH" \
    --experiment "$EXPERIMENT" \
    --output-dir "$OUTPUT_DIR/03a_correlation_analysis_original"

# 3b. Analyze training loss correlations (v2 with hyperparameter handling)
echo -e "\n3b. Analyzing training loss correlations (v2 - hyperparameter aware)..."
uv run python scripts/analyze_regression_correlations_v2.py \
    --base-path "$BASE_PATH" \
    --experiment "$EXPERIMENT" \
    --output-dir "$OUTPUT_DIR/03b_correlation_analysis_v2"

# 4. Analyze validation loss correlations
echo -e "\n4. Analyzing validation loss correlations..."
uv run python scripts/analyze_val_loss_regression_correlations.py \
    --base-path "$BASE_PATH" \
    --experiment "$EXPERIMENT" \
    --output-dir "$OUTPUT_DIR/04_val_loss_correlation_analysis"

# 5a. Analyze early regression correlations (original)
echo -e "\n5a. Analyzing early regression correlations (original grouping)..."
uv run python scripts/analyze_early_regression_correlations.py \
    --base-path "$BASE_PATH" \
    --experiment "$EXPERIMENT" \
    --output-dir "$OUTPUT_DIR/05a_early_correlation_analysis_original"

# 5b. Analyze early regression correlations (v2 with hyperparameter handling)
echo -e "\n5b. Analyzing early regression correlations (v2 - hyperparameter aware)..."
uv run python scripts/analyze_early_regression_correlations_v2.py \
    --base-path "$BASE_PATH" \
    --experiment "$EXPERIMENT" \
    --output-dir "$OUTPUT_DIR/05b_early_correlation_analysis_v2"

echo -e "\nAll analyses complete! Results saved in $OUTPUT_DIR/"
echo -e "\nRecommended viewing order:"
echo "1. 05b_early_correlation_analysis_v2/ - Early training dynamics vs final performance (NEW)"
echo "   - Shows how first 10 epochs predict final accuracy"
echo "   - Properly separates different hyperparameter sweeps"
echo "2. 03b_correlation_analysis_v2/ - Full training regression analysis (NEW)"
echo "   - Complete training curve analysis with hyperparameter variations"
echo "3. 01_line_plots/ - Raw training curves for visual inspection"
echo "4. Compare 03a vs 03b and 05a vs 05b to see impact of proper hyperparameter handling"
echo ""
echo "Key insights to look for:"
echo "- Which early metrics best predict final performance?"
echo "- How do different learning rates affect the regression patterns?"
echo "- Do controlled experiments show different patterns than the step-wise removal?"
