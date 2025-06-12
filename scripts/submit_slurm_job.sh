#!/bin/bash
# Wrapper script to submit SLURM job with explicit environment variables
# This is the MOST RELIABLE way to pass environment variables to SLURM

# Default values
DEFAULT_BASE_PATH="/scratch/ddr8143/logs/dcnn_workers/"
DEFAULT_EXPERIMENT="cluster_t0"
DEFAULT_WORKERS_PER_GPU=2
DEFAULT_GPUS=1

# Parse command line arguments
BASE_PATH=${1:-$DEFAULT_BASE_PATH}
EXPERIMENT=${2:-$DEFAULT_EXPERIMENT}
WORKERS_PER_GPU=${3:-$DEFAULT_WORKERS_PER_GPU}
GPUS=${4:-$DEFAULT_GPUS}

echo "=== Submitting DR_EXP SLURM Job ==="
echo "Base path: $BASE_PATH"
echo "Experiment: $EXPERIMENT"
echo "Workers per GPU: $WORKERS_PER_GPU"
echo "GPUs requested: $GPUS"
echo ""

# Method 1: Export variables before sbatch (most reliable)
export BASE_PATH
export EXPERIMENT
export WORKERS_PER_GPU

# Method 2: Also pass them explicitly with --export
# Using the format --export=ALL,VAR1=value1,VAR2=value2
sbatch \
    --job-name="dr_exp_${EXPERIMENT}" \
    --gres=gpu:rtx8000:${GPUS} \
    --export=ALL,BASE_PATH="$BASE_PATH",EXPERIMENT="$EXPERIMENT",WORKERS_PER_GPU="$WORKERS_PER_GPU" \
    scripts/slurm_job_safe.sbatch

echo ""
echo "To monitor job:"
echo "  squeue -u $USER"
echo "  tail -f /scratch/ddr8143/logs/slurm_logs/dr_exp_${EXPERIMENT}_*.out"