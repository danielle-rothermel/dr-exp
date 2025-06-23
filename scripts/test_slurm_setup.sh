#!/bin/bash
# Test script to verify SLURM setup before full experiment

# Test configuration
BASE_PATH="/scratch/ddr8143/repos/dr_exp/test_run"
EXPERIMENT="slurm_test"
PROJECT_DIR="/scratch/ddr8143/repos/dr_exp"

echo "=== SLURM Setup Test ==="
echo "This will submit one test job and process it"

# Step 1: Setup environment
cd $PROJECT_DIR
source .venv/bin/activate
source .env

# Step 2: Initialize experiment
echo "Initializing experiment..."
dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" init

# Step 3: Submit one test job
echo "Submitting test job..."
dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" job submit \
    --config-path exp_configs \
    --config-name step00_baseline \
    --overrides "epochs=1 limit_train_batches=10 limit_val_batches=5" \
    --priority 100

# Step 4: Check submission
JOB_COUNT=$(dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" list --status queued | grep -c "queued" || echo 0)
echo "Queued jobs: $JOB_COUNT"

if [ "$JOB_COUNT" -eq 0 ]; then
    echo "ERROR: Job submission failed!"
    exit 1
fi

# Step 5: Submit minimal SLURM job
echo "Submitting SLURM worker job..."
sbatch <<EOF
#!/bin/bash
#SBATCH --job-name=dr_exp_test
#SBATCH --time=1:00:00
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --output=$PROJECT_DIR/test_slurm_%j.out

cd $PROJECT_DIR
source .venv/bin/activate
source .env

echo "Worker starting on node: \$(hostname)"
echo "GPU: \$(nvidia-smi --query-gpu=name --format=csv,noheader)"

dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" worker \
    --worker-id "test_worker_\${SLURM_JOB_ID}" \
    --max-jobs 1
EOF

echo ""
echo "Test submitted! Monitor with:"
echo "  squeue -u $USER"
echo "  tail -f $PROJECT_DIR/test_slurm_*.out"