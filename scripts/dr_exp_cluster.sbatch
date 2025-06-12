#!/bin/bash
#SBATCH --job-name="dr_exp_workers"
#SBATCH --open-mode=append
#SBATCH --output=/scratch/ddr8143/logs/slurm_logs/%x_s%a_%A.out
#SBATCH --error=/scratch/ddr8143/logs/slurm_logs/%x_s%a_%A.err
#SBATCH --export=ALL
#SBATCH --time=47:00:00
#SBATCH --gres=gpu:rtx8000:2
#SBATCH --mem=80G
#SBATCH --nodes=1
#SBATCH --tasks-per-node=1
#SBATCH --cpus-per-task=12
#SBATCH --account=cds

# Parameters that can be overridden
BASE_PATH=${BASE_PATH:-/scratch/ddr8143/repos/dr_exp/chronological_ablation}
EXPERIMENT=${EXPERIMENT:-main}
WORKERS_PER_GPU=${WORKERS_PER_GPU:-3}

# Setup CUDA MPS for better GPU sharing
export CUDA_MPS_PIPE_DIRECTORY="/tmp/nvidia-mps-${SLURM_JOB_ID}"
export CUDA_MPS_LOG_DIRECTORY="/tmp/nvidia-log-${SLURM_JOB_ID}"
mkdir -p "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"

# Start MPS daemon
nvidia-cuda-mps-control -d

# Cleanup function for MPS
cleanup_mps() {
    echo "Cleaning up CUDA MPS..."
    echo quit | nvidia-cuda-mps-control 2>/dev/null || true
    rm -rf "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"
}
trap cleanup_mps EXIT

singularity exec --nv --overlay $SCRATCH/drexp.ext3:ro /scratch/work/public/singularity/cuda11.8.86-cudnn8.7-devel-ubuntu22.04.2.sif /bin/bash -c "
source /scratch/ddr8143/repos/dr_exp/.venv/bin/activate
cd /scratch/ddr8143/repos/dr_exp

# Load environment variables
source .env

# Export Supabase credentials
export SUPABASE_URL=$SUPABASE_URL
export SUPABASE_KEY=$SUPABASE_KEY

# Log startup info
echo '========================================'
echo 'DR_EXP Worker Launch'
echo '========================================'
echo 'Time: $(date)'
echo 'Base path: $BASE_PATH'
echo 'Experiment: $EXPERIMENT'
echo 'Workers per GPU: $WORKERS_PER_GPU'
echo 'CUDA MPS: Enabled'
echo '========================================'

# Check for existing jobs
echo 'Checking job queue...'
uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT status

# Launch workers
echo 'Starting launcher...'
uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT system launcher --workers-per-gpu $WORKERS_PER_GPU --max-hours 46
"