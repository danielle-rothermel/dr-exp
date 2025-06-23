#!/bin/bash
#SBATCH --job-name=dr_exp_workers
#SBATCH --output=/scratch/ddr8143/repos/dr_exp/logs/%x_%j.out
#SBATCH --error=/scratch/ddr8143/repos/dr_exp/logs/%x_%j.err
#SBATCH --time=47:00:00
#SBATCH --gres=gpu:rtx8000:2
#SBATCH --mem=80G
#SBATCH --nodes=1
#SBATCH --tasks-per-node=1
#SBATCH --cpus-per-task=12
#SBATCH --account=cds

# Configuration
BASE_PATH=${BASE_PATH:-/scratch/ddr8143/repos/dr_exp/chronological_ablation}
EXPERIMENT=${EXPERIMENT:-main}
WORKERS_PER_GPU=${WORKERS_PER_GPU:-6}
PROJECT_DIR="/scratch/ddr8143/repos/dr_exp"

# Log startup info
echo "========================================
DR_EXP Worker Launch
========================================
Job ID: $SLURM_JOB_ID
Node: $SLURMD_NODENAME
Time: $(date)
Base path: $BASE_PATH
Experiment: $EXPERIMENT
Workers per GPU: $WORKERS_PER_GPU
GPUs: $SLURM_GPUS_PER_NODE
Memory: $SLURM_MEM_PER_NODE MB
========================================"

# Create necessary directories
mkdir -p "$BASE_PATH/$EXPERIMENT/logs"
mkdir -p "$BASE_PATH/$EXPERIMENT/control"

# Setup CUDA MPS for better GPU sharing
export CUDA_MPS_PIPE_DIRECTORY="/tmp/nvidia-mps-${SLURM_JOB_ID}"
export CUDA_MPS_LOG_DIRECTORY="/tmp/nvidia-log-${SLURM_JOB_ID}"
mkdir -p "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"

cleanup() {
    echo "Cleaning up CUDA MPS..."
    echo quit | nvidia-cuda-mps-control 2>/dev/null || true
    rm -rf "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"
}
trap cleanup EXIT

# Start CUDA MPS daemon
nvidia-cuda-mps-control -d

# Launch workers in singularity container
singularity exec --nv \
    --overlay $SCRATCH/drexp.ext3:ro \
    --bind "$PROJECT_DIR:$PROJECT_DIR" \
    --bind "$BASE_PATH:$BASE_PATH" \
    --pwd "$PROJECT_DIR" \
    /scratch/work/public/singularity/cuda11.8.86-cudnn8.7-devel-ubuntu22.04.2.sif \
    /bin/bash -c "
# Setup environment
cd $PROJECT_DIR
source .venv/bin/activate
source .env

# Verify environment
echo 'Python: $(which python)'
echo 'dr_exp: $(which dr_exp)'

# Check for queued jobs
JOB_COUNT=\$(dr_exp --base-path \"$BASE_PATH\" --experiment \"$EXPERIMENT\" list --status queued | grep -c \"queued\" || echo 0)
echo \"Found \$JOB_COUNT queued jobs\"

if [ \"\$JOB_COUNT\" -eq 0 ]; then
    echo \"WARNING: No queued jobs found!\"
    echo \"Did you run submit_experiments.sh first?\"
    echo \"Continuing anyway in case jobs are submitted later...\"
fi

# Launch workers
echo \"Starting launcher with $WORKERS_PER_GPU workers per GPU...\"
dr_exp --base-path \"$BASE_PATH\" \
       --experiment \"$EXPERIMENT\" \
       system launcher \
       --workers-per-gpu \"$WORKERS_PER_GPU\" \
       --max-hours 46
"