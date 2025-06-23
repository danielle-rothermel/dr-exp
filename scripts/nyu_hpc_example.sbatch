#!/bin/bash
#SBATCH --job-name=dr_exp_worker
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32GB
#SBATCH --time=48:00:00
#SBATCH --gres=gpu:1
#SBATCH --partition=gpu  # Adjust based on NYU partitions

# Load any required modules
# module load python/3.10  # If needed

# Change to project directory
cd /scratch/ddr8143/repos/dr_exp

# Load environment variables from .env
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Log some info
echo "Starting dr_exp worker on $(hostname)"
echo "GPU info:"
nvidia-smi --query-gpu=name,memory.total --format=csv

# Set experiment paths
BASE_PATH="/scratch/ddr8143/experiments"
EXPERIMENT="my_experiment"

# Option 1: Run a single worker
uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT worker \
    --worker-id "worker_${SLURM_JOB_ID}_${SLURM_ARRAY_TASK_ID:-0}" \
    --working-dir "/scratch/ddr8143/work/${SLURM_JOB_ID}"

# Option 2: Run multi-worker launcher (auto-detects GPUs)
# uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT \
#     system launcher --workers-per-gpu 2