#!/bin/bash
#SBATCH --job-name=dr_exp_manager
# Add cluster-specific SBATCH directives here

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

# TODO: environment setup (modules, secrets) goes here

# Launch the run manager
uv run python scripts/run_manager.py "$@"
