#!/bin/bash
#SBATCH --job-name="dr_exp_high_share"
#SBATCH --open-mode=append
#SBATCH --output=/scratch/ddr8143/logs/slurm_logs/%x_s%a_%A.out
#SBATCH --error=/scratch/ddr8143/logs/slurm_logs/%x_s%a_%A.err
#SBATCH --export=ALL
#SBATCH --time=47:00:00
#SBATCH --gres=gpu:rtx8000:1
#SBATCH --mem=80G
#SBATCH --nodes=1
#SBATCH --tasks-per-node=1
#SBATCH --cpus-per-task=12
#SBATCH --account=cds

# Parameters - 6 workers on 1 GPU for maximum throughput
BASE_PATH=${BASE_PATH:-/scratch/ddr8143/repos/dr_exp/chronological_ablation}
EXPERIMENT=${EXPERIMENT:-main}
WORKERS_PER_GPU=${WORKERS_PER_GPU:-6}

# Setup CUDA MPS for aggressive GPU sharing
export CUDA_MPS_PIPE_DIRECTORY="/tmp/nvidia-mps-${SLURM_JOB_ID}"
export CUDA_MPS_LOG_DIRECTORY="/tmp/nvidia-log-${SLURM_JOB_ID}"
mkdir -p "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"

# Configure MPS for better sharing with many processes
export CUDA_MPS_ACTIVE_THREAD_PERCENTAGE=100  # Allow full GPU utilization
export CUDA_DEVICE_DEFAULT_PERSISTING_L2_CACHE_PERCENTAGE_LIMIT=0  # Disable L2 persistence

# Start MPS daemon
nvidia-cuda-mps-control -d

# Set MPS thread percentage per client (with 6 workers, each gets ~16%)
echo "set_default_active_thread_percentage 16" | nvidia-cuda-mps-control

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
export SUPABASE_URL=$SUPABASE_URL
export SUPABASE_KEY=$SUPABASE_KEY

# Additional env vars for better GPU sharing
export CUDA_LAUNCH_BLOCKING=0  # Allow concurrent kernel execution
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512  # Smaller memory chunks

echo '========================================'
echo 'DR_EXP High GPU Sharing Mode'
echo '========================================'
echo 'Time: $(date)'
echo 'Base path: $BASE_PATH'
echo 'Experiment: $EXPERIMENT'
echo 'Workers per GPU: $WORKERS_PER_GPU'
echo 'CUDA MPS: Enabled (16% per worker)'
echo 'GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader)'
echo '========================================'

# Check for existing jobs
echo 'Checking job queue...'
uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT status

# Launch workers with high sharing
echo 'Starting launcher with aggressive GPU sharing...'
uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT system launcher --workers-per-gpu $WORKERS_PER_GPU --max-hours 46
"