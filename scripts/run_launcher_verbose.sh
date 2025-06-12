#!/bin/bash
# Run launcher with verbose Python logging

BASE_PATH=${BASE_PATH:-/scratch/ddr8143/repos/dr_exp/chronological_ablation}
EXPERIMENT=${EXPERIMENT:-main}
WORKERS_PER_GPU=${WORKERS_PER_GPU:-3}

echo "=== Running launcher with verbose logging ==="
echo "Base path: $BASE_PATH"
echo "Experiment: $EXPERIMENT"
echo "Workers per GPU: $WORKERS_PER_GPU"
echo ""

# Check if experiment exists
if [ ! -d "$BASE_PATH/$EXPERIMENT" ]; then
    echo "ERROR: Experiment directory doesn't exist!"
    exit 1
fi

# Check for jobs
echo "Checking job queue..."
cd /scratch/ddr8143/repos/dr_exp
source .venv/bin/activate

JOB_COUNT=$(dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" list --status queued | grep -c "queued" || echo 0)
echo "Queued jobs: $JOB_COUNT"

if [ "$JOB_COUNT" -eq 0 ]; then
    echo "WARNING: No queued jobs!"
fi

# Set Python logging to DEBUG
export PYTHONUNBUFFERED=1
export DR_EXP_LOG_LEVEL=DEBUG

echo ""
echo "Starting launcher with debug logging..."
echo "========================================="

# Run with Python verbose mode
python -u -m dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" system launcher \
    --workers-per-gpu "$WORKERS_PER_GPU" \
    --max-hours 46 2>&1 | tee launcher_verbose.log