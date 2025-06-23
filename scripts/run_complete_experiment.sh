#!/bin/bash
# Complete experiment runner with proper SLURM environment handling
# This script submits jobs and launches workers reliably

set -e  # Exit on error

# Configuration
EXPERIMENT_NAME=${1:-main}
WORKERS_PER_GPU=${2:-3}
NUM_GPUS=${3:-2}
BASE_PATH="/scratch/ddr8143/repos/dr_exp/chronological_ablation"

echo "=== DR_EXP Complete Experiment Runner ==="
echo "Experiment: $EXPERIMENT_NAME"
echo "Base path: $BASE_PATH"
echo "Workers per GPU: $WORKERS_PER_GPU"
echo "GPUs requested: $NUM_GPUS"
echo "Total workers: $((WORKERS_PER_GPU * NUM_GPUS))"
echo ""

# Step 1: Activate environment and submit jobs
cd /scratch/ddr8143/repos/dr_exp
source .venv/bin/activate

# Check if experiment exists, if not initialize it
if [ ! -d "$BASE_PATH/$EXPERIMENT_NAME" ]; then
    echo "Initializing new experiment..."
    dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT_NAME" init
fi

# Submit experiment jobs
echo "Step 1: Submitting experiment jobs..."
python scripts/submit_experiments.sh

# Verify jobs were submitted
JOB_COUNT=$(dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT_NAME" job list --status queued | grep -c "queued" || echo 0)
echo "Queued jobs: $JOB_COUNT"

if [ "$JOB_COUNT" -eq 0 ]; then
    echo "ERROR: No jobs were queued!"
    exit 1
fi

# Step 2: Submit SLURM worker job using embedded method (most reliable)
echo ""
echo "Step 2: Submitting SLURM worker job..."

# Use the embedded script method for maximum reliability
JOBID=$(./scripts/submit_slurm_embedded.sh "$BASE_PATH" "$EXPERIMENT_NAME" "$WORKERS_PER_GPU" "$NUM_GPUS" | grep "Submitted job:" | awk '{print $3}')

if [ -z "$JOBID" ]; then
    echo "ERROR: Failed to submit SLURM job!"
    exit 1
fi

echo "SLURM Job ID: $JOBID"

# Step 3: Provide monitoring information
echo ""
echo "=== Experiment Launched Successfully! ==="
echo ""
echo "Monitor your experiment:"
echo ""
echo "1. SLURM job status:"
echo "   squeue -j $JOBID"
echo ""
echo "2. Experiment progress:"
echo "   ./scripts/monitor_launcher.sh $BASE_PATH $EXPERIMENT_NAME"
echo ""
echo "3. SLURM output log:"
echo "   tail -f /scratch/ddr8143/logs/slurm_logs/dr_exp_${EXPERIMENT_NAME}_${JOBID}.out"
echo ""
echo "4. Worker logs:"
echo "   ls -la $BASE_PATH/$EXPERIMENT_NAME/logs/"
echo ""
echo "5. Job status summary:"
echo "   watch -n 10 'dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT_NAME status'"
echo ""
echo "6. GPU utilization:"
echo "   ./scripts/monitor_gpu_sharing.sh"
echo ""
echo "To stop the experiment gracefully:"
echo "   touch $BASE_PATH/$EXPERIMENT_NAME/control/stop_$JOBID"
echo ""
echo "Expected runtime: ~47 hours for all 54 jobs (18 configs × 3 seeds)"