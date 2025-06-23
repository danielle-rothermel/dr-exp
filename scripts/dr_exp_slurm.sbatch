#!/bin/bash
#SBATCH --job-name=dr_exp_workers
#SBATCH --time=47:00:00
#SBATCH --nodes=1
#SBATCH --gpus-per-node=3
#SBATCH --cpus-per-task=8
#SBATCH --mem=192G

# Parameters from environment or defaults
BASE_PATH=${BASE_PATH:-/scratch/users/$USER/experiments}
EXPERIMENT=${EXPERIMENT:-default_experiment}
WORKERS_PER_GPU=${WORKERS_PER_GPU:-2}

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

# Setup Python environment (adjust as needed)
module load python/3.10
source /path/to/venv/bin/activate

# Optional: Setup CUDA MPS for better GPU sharing
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

# Start launcher with enhanced logging
dr_exp --base-path "$BASE_PATH" \
       --experiment "$EXPERIMENT" \
       system launcher \
       --workers-per-gpu "$WORKERS_PER_GPU" \
       2>&1 | tee -a "$LOG_DIR/launcher.log"

echo "SLURM job completed at $(date)"