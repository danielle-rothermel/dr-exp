#!/bin/bash
# Helper script to submit multiple experiments

set -e

# Default values
BASE_PATH="${BASE_PATH:-/scratch/users/$USER/experiments}"
WORKERS_PER_GPU="${WORKERS_PER_GPU:-2}"
SLURM_SCRIPT="scripts/dr_exp_slurm.sbatch"

# Function to submit a single experiment
submit_experiment() {
    local exp_name=$1
    local priority=${2:-100}
    
    echo "Submitting experiment: $exp_name (priority: $priority)"
    
    # Create experiment directory
    mkdir -p "$BASE_PATH/$exp_name"
    
    # Submit SLURM job
    job_id=$(sbatch \
        --export=BASE_PATH="$BASE_PATH",EXPERIMENT="$exp_name",WORKERS_PER_GPU="$WORKERS_PER_GPU" \
        --job-name="dr_exp_$exp_name" \
        "$SLURM_SCRIPT" | awk '{print $NF}')
    
    echo "  Submitted SLURM job: $job_id"
    
    # Create a tracking file
    echo "$job_id" > "$BASE_PATH/$exp_name/.slurm_job_id"
}

# Check arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 experiment1 [experiment2 ...]"
    echo "  or: $0 -f experiments.txt"
    exit 1
fi

# Process arguments
if [ "$1" = "-f" ]; then
    # Read from file
    if [ ! -f "$2" ]; then
        echo "Error: File $2 not found"
        exit 1
    fi
    
    while IFS= read -r exp_name; do
        [ -z "$exp_name" ] && continue  # Skip empty lines
        [[ "$exp_name" =~ ^# ]] && continue  # Skip comments
        submit_experiment "$exp_name"
    done < "$2"
else
    # Submit each argument as experiment
    for exp_name in "$@"; do
        submit_experiment "$exp_name"
    done
fi

echo "All experiments submitted"