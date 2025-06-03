#!/bin/bash
#SBATCH --job-name=dr_exp_manager
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

set -euo pipefail

# Setup unique pipe and log directories for this job to avoid conflicts
# and ensure cleanup targets the correct daemon.
export CUDA_MPS_PIPE_DIRECTORY="/tmp/nvidia-mps-${SLURM_JOB_ID}"
export CUDA_MPS_LOG_DIRECTORY="/tmp/nvidia-log-${SLURM_JOB_ID}"
mkdir -p "$CUDA_MPS_PIPE_DIRECTORY"
mkdir -p "$CUDA_MPS_LOG_DIRECTORY"

cleanup_mps() {
    echo quit | nvidia-cuda-mps-control
    rm -rf "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"
}

trap cleanup_mps EXIT SIGINT SIGTERM

# Start the CUDA MPS control daemon
nvidia-cuda-mps-control -d

# Launch the run manager
singularity exec --nv --overlay $SCRATCH/continual_learning_v2.ext3:ro /scratch/work/public/singularity/cuda11.8.86-cudnn8.7-devel-ubuntu22.04.2.sif /bin/bash -c "
source /scratch/ddr8143/repos/dr_gen/.venv/bin/activate
python scripts/run_manager.py $@
"
