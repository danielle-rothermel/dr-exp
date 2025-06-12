#!/bin/bash
# Script to submit experiments and then launch SLURM workers
# Usage: ./submit_and_run.sh [experiment_name]

EXPERIMENT=${1:-main}
BASE_PATH="/scratch/ddr8143/repos/dr_exp/chronological_ablation"

echo "=== DR_EXP Experiment Runner ==="
echo "Experiment: $EXPERIMENT"
echo "Base path: $BASE_PATH"

# Step 1: Activate environment and submit jobs
cd /scratch/ddr8143/repos/dr_exp
source .venv/bin/activate

echo ""
echo "Step 1: Submitting experiment jobs..."
python scripts/submit_experiments.sh

# Check submission
JOB_COUNT=$(uv run dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" list --status queued | grep -c "queued" || echo 0)
echo "Queued jobs: $JOB_COUNT"

if [ "$JOB_COUNT" -eq 0 ]; then
    echo "ERROR: No jobs were submitted!"
    exit 1
fi

# Step 2: Submit SLURM job
echo ""
echo "Step 2: Submitting SLURM worker job..."

# Export parameters for SLURM job
export BASE_PATH
export EXPERIMENT
export WORKERS_PER_GPU=3  # 3 workers per GPU for 2 GPUs = 6 total workers

SLURM_JOB_ID=$(sbatch --parsable scripts/dr_exp_cluster.sbatch)
echo "SLURM Job ID: $SLURM_JOB_ID"

# Step 3: Provide monitoring info
echo ""
echo "=== Monitoring Commands ==="
echo "Job status:     squeue -u $USER"
echo "Experiment:     watch -n 10 'uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT status'"
echo "SLURM output:   tail -f /scratch/ddr8143/logs/slurm_logs/dr_exp_workers_s_${SLURM_JOB_ID}.out"
echo "Worker logs:    ls -la $BASE_PATH/$EXPERIMENT/logs/"