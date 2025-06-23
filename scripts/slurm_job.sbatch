#!/bin/bash
#SBATCH --job-name=dr_exp_manager
#SBATCH --open-mode=append
#SBATCH --output=/scratch/ddr8143/logs/slurm_logs/%x_s%a_%A.out
#SBATCH --error=/scratch/ddr8143/logs/slurm_logs/%x_s%a_%A.err
#SBATCH --export=ALL
#SBATCH --time=47:00:00
#SBATCH --gres=gpu:rtx8000:1
#SBATCH --mem=60G
#SBATCH --nodes=1
#SBATCH --tasks-per-node=1
#SBATCH --cpus-per-task=10
#SBATCH --account=cds

# Parameters from environment or defaults
BASE_PATH=${BASE_PATH:-/scratch/ddr8143/logs/dcnn_workers/}
EXPERIMENT=${EXPERIMENT:-cluster_t0}
WORKERS_PER_GPU=${WORKERS_PER_GPU:-1}


# Create log directory for this SLURM job
LOG_DIR="$BASE_PATH/$EXPERIMENT/logs/slurm_${SLURM_JOB_ID}"
mkdir -p "$LOG_DIR/workers"
mkdir -p "$BASE_PATH/$EXPERIMENT/control"

# Redirect SLURM output
SLURM_LOG_DIR="$BASE_PATH/$EXPERIMENT/slurm_logs"
mkdir -p "$SLURM_LOG_DIR"
exec &> >(tee -a "$SLURM_LOG_DIR/slurm-${SLURM_JOB_ID}.out")

# Log startup info
echo "========================================"
echo "DR_EXP SLURM Job Starting"
echo "========================================"
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Time: $(date)"
echo "Base path: $BASE_PATH"
echo "Experiment: $EXPERIMENT"
echo "Workers per GPU: $WORKERS_PER_GPU"
echo "Allocated GPUs: $SLURM_GPUS_PER_NODE"
echo "Allocated Memory: $SLURM_MEM_PER_NODE MB"
echo "Log directory: $LOG_DIR"
echo "========================================"

# Setup CUDA MPS for better GPU sharing (REQUIRED for multiple workers per GPU)
export CUDA_MPS_PIPE_DIRECTORY="/tmp/nvidia-mps-${SLURM_JOB_ID}"
export CUDA_MPS_LOG_DIRECTORY="/tmp/nvidia-log-${SLURM_JOB_ID}"
mkdir -p "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"

cleanup() {
    echo "Cleaning up..."
    echo quit | nvidia-cuda-mps-control 2>/dev/null || true
    rm -rf "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"
}
trap cleanup EXIT

# Start CUDA MPS daemon
nvidia-cuda-mps-control -d
echo "CUDA MPS started for GPU sharing"

echo "Launching singularity container..."

# Launch the run manager
singularity exec --nv --overlay $SCRATCH/drexp.ext3:ro /scratch/work/public/singularity/cuda11.8.86-cudnn8.7-devel-ubuntu22.04.2.sif /bin/bash -c "
source /scratch/ddr8143/repos/dr_exp/.venv/bin/activate
cd /scratch/ddr8143/repos/dr_exp
source .env
export SUPABASE_URL=$SUPABASE_URL
export SUPABASE_KEY=$SUPABASE_KEY
echo 'Starting workers with Supabase sync enabled...'
echo 'SUPABASE_URL: ${SUPABASE_URL:0:30}...'
dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT system launcher --workers-per-gpu $WORKERS_PER_GPU --max-hours 46
"
