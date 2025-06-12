#!/bin/bash
#SBATCH --job-name="dr_exp_test"
#SBATCH --open-mode=append
#SBATCH --output=/scratch/ddr8143/logs/slurm_logs/%x_s%a_%A.out
#SBATCH --error=/scratch/ddr8143/logs/slurm_logs/%x_s%a_%A.err
#SBATCH --export=ALL
#SBATCH --time=00:30:00
#SBATCH --gres=gpu:rtx8000:1
#SBATCH --mem=32G
#SBATCH --nodes=1
#SBATCH --tasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --account=cds

singularity exec --nv --overlay $SCRATCH/drexp.ext3:ro /scratch/work/public/singularity/cuda11.8.86-cudnn8.7-devel-ubuntu22.04.2.sif /bin/bash -c "
source /scratch/ddr8143/repos/dr_exp/.venv/bin/activate
cd /scratch/ddr8143/repos/dr_exp

# Test basic environment
echo '=== Environment Test ==='
echo 'Python: $(which python)'
echo 'dr_exp: $(which dr_exp)'
nvidia-smi --query-gpu=name,memory.total --format=csv

# Test dr_exp command
echo ''
echo '=== Testing dr_exp CLI ==='
uv run dr_exp --help

# Test with a minimal job
BASE_PATH=/scratch/ddr8143/repos/dr_exp/test_cluster
EXPERIMENT=cluster_test

echo ''
echo '=== Initializing test experiment ==='
uv run dr_exp --base-path \$BASE_PATH --experiment \$EXPERIMENT init

echo ''
echo '=== Submitting test job ==='
uv run dr_exp --base-path \$BASE_PATH --experiment \$EXPERIMENT job submit \
    --config-path exp_configs \
    --config-name step00_baseline \
    --overrides 'epochs=1 limit_train_batches=5' \
    --priority 100

echo ''
echo '=== Running worker ==='
uv run dr_exp --base-path \$BASE_PATH --experiment \$EXPERIMENT worker \
    --worker-id test_worker_\${SLURM_JOB_ID} \
    --max-jobs 1

echo ''
echo '=== Test complete ==='
"