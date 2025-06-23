#!/bin/bash
# Run all regression analyses for an experiment

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

echo "Running all analyses for experiment: $EXPERIMENT"
echo "Base path: $BASE_PATH"
echo ""

# 1. Create line plots
echo "1. Creating line plots..."
uv run python scripts/create_line_plots.py \
    --base-path "$BASE_PATH" \
    --experiment "$EXPERIMENT" \
    --output-dir "na_full_t0/${EXPERIMENT}_line_plots"

# 2. Create training loss regression plots
echo -e "\n2. Creating training loss regression plots..."
uv run python scripts/create_training_loss_regression_plots.py \
    --base-path "$BASE_PATH" \
    --experiment "$EXPERIMENT" \
    --output-dir "na_full_t0/${EXPERIMENT}_regression_plots"

# 3. Analyze training loss correlations
echo -e "\n3. Analyzing training loss correlations..."
uv run python scripts/analyze_regression_correlations.py \
    --base-path "$BASE_PATH" \
    --experiment "$EXPERIMENT" \
    --output-dir "na_full_t0/${EXPERIMENT}_correlation_analysis"

# 4. Analyze validation loss correlations
echo -e "\n4. Analyzing validation loss correlations..."
uv run python scripts/analyze_val_loss_regression_correlations.py \
    --base-path "$BASE_PATH" \
    --experiment "$EXPERIMENT" \
    --output-dir "na_full_t0/${EXPERIMENT}_val_loss_correlation_analysis"

echo -e "\nAll analyses complete! Results saved in:"
echo "  - ${EXPERIMENT}_line_plots/"
echo "  - ${EXPERIMENT}_regression_plots/"
echo "  - ${EXPERIMENT}_correlation_analysis/"
echo "  - ${EXPERIMENT}_val_loss_correlation_analysis/"
