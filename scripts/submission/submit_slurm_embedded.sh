#!/bin/bash
# Alternative method: Generate sbatch script with embedded parameters
# This is 100% reliable since no environment variables are needed

# Configuration
BASE_PATH=${1:-/scratch/ddr8143/logs/dcnn_workers/}
EXPERIMENT=${2:-cluster_t0}
WORKERS_PER_GPU=${3:-2}
GPUS=${4:-1}

echo "=== Generating and submitting SLURM job ==="
echo "Base path: $BASE_PATH"
echo "Experiment: $EXPERIMENT"
echo "Workers per GPU: $WORKERS_PER_GPU"
echo "GPUs: $GPUS"

# Create temporary sbatch script with all values embedded
TEMP_SCRIPT="/tmp/dr_exp_${EXPERIMENT}_$$.sbatch"

cat > "$TEMP_SCRIPT" << EOF
#!/bin/bash
#SBATCH --job-name=dr_exp_${EXPERIMENT}
#SBATCH --open-mode=append
#SBATCH --output=/scratch/ddr8143/logs/slurm_logs/%x_%j.out
#SBATCH --error=/scratch/ddr8143/logs/slurm_logs/%x_%j.err
#SBATCH --time=47:00:00
#SBATCH --gres=gpu:rtx8000:${GPUS}
#SBATCH --mem=60G
#SBATCH --nodes=1
#SBATCH --tasks-per-node=1
#SBATCH --cpus-per-task=10
#SBATCH --account=cds

# All parameters are embedded - no environment variables needed
BASE_PATH="${BASE_PATH}"
EXPERIMENT="${EXPERIMENT}"
WORKERS_PER_GPU="${WORKERS_PER_GPU}"

echo "========================================"
echo "DR_EXP SLURM Job Starting"
echo "========================================"
echo "Job ID: \$SLURM_JOB_ID"
echo "Node: \$SLURMD_NODENAME"
echo "Time: \$(date)"
echo "Base path: \$BASE_PATH"
echo "Experiment: \$EXPERIMENT"
echo "Workers per GPU: \$WORKERS_PER_GPU"
echo "========================================"

# Create directories
mkdir -p "\$BASE_PATH/\$EXPERIMENT/logs"
mkdir -p "\$BASE_PATH/\$EXPERIMENT/control"

# Setup CUDA MPS
export CUDA_MPS_PIPE_DIRECTORY="/tmp/nvidia-mps-\${SLURM_JOB_ID}"
export CUDA_MPS_LOG_DIRECTORY="/tmp/nvidia-log-\${SLURM_JOB_ID}"
mkdir -p "\$CUDA_MPS_PIPE_DIRECTORY" "\$CUDA_MPS_LOG_DIRECTORY"

cleanup() {
    echo "Cleaning up..."
    echo quit | nvidia-cuda-mps-control 2>/dev/null || true
    rm -rf "\$CUDA_MPS_PIPE_DIRECTORY" "\$CUDA_MPS_LOG_DIRECTORY"
}
trap cleanup EXIT

nvidia-cuda-mps-control -d
echo "CUDA MPS started"

# Launch in singularity
singularity exec --nv --overlay \$SCRATCH/drexp.ext3:ro /scratch/work/public/singularity/cuda11.8.86-cudnn8.7-devel-ubuntu22.04.2.sif /bin/bash -c "
source /scratch/ddr8143/repos/dr_exp/.venv/bin/activate
cd /scratch/ddr8143/repos/dr_exp
source .env

echo 'Starting launcher...'
uv run dr_exp --base-path ${BASE_PATH} --experiment ${EXPERIMENT} system launcher --workers-per-gpu ${WORKERS_PER_GPU} --max-hours 46
"
EOF

# Submit the generated script
echo ""
echo "Submitting generated script: $TEMP_SCRIPT"
JOBID=$(sbatch --parsable "$TEMP_SCRIPT")
echo "Submitted job: $JOBID"

# Clean up
rm "$TEMP_SCRIPT"

echo ""
echo "Monitor with:"
echo "  squeue -j $JOBID"
echo "  tail -f /scratch/ddr8143/logs/slurm_logs/dr_exp_${EXPERIMENT}_${JOBID}.out"