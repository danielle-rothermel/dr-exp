#!/bin/bash
# Full experiment runner - submits jobs then launches SLURM workers

# Configuration
BASE_PATH="/scratch/ddr8143/repos/dr_exp/chronological_ablation"
EXPERIMENT="main"
WORKERS_PER_GPU=6
GPUS_REQUESTED=2

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== DR_EXP Full Experiment Runner ===${NC}"
echo "Base path: $BASE_PATH"
echo "Experiment: $EXPERIMENT"

# Step 1: Submit all experiment jobs
echo -e "\n${GREEN}Step 1: Submitting experiment jobs...${NC}"
cd /scratch/ddr8143/repos/dr_exp
source .venv/bin/activate

python scripts/submit_experiments.sh

# Check if jobs were submitted
JOB_COUNT=$(dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" list --status queued | grep -c "queued" || echo 0)
echo -e "\n${GREEN}Queued jobs: $JOB_COUNT${NC}"

if [ "$JOB_COUNT" -eq 0 ]; then
    echo -e "${RED}ERROR: No jobs were submitted!${NC}"
    exit 1
fi

# Step 2: Submit SLURM job to process them
echo -e "\n${GREEN}Step 2: Submitting SLURM worker job...${NC}"

# Export variables for SLURM job
export BASE_PATH
export EXPERIMENT  
export WORKERS_PER_GPU

# Submit the job
SLURM_JOB_ID=$(sbatch \
    --parsable \
    --job-name="dr_exp_${EXPERIMENT}" \
    --gres=gpu:rtx8000:${GPUS_REQUESTED} \
    scripts/slurm_job_improved.sbatch)

echo -e "${GREEN}SLURM Job ID: $SLURM_JOB_ID${NC}"

# Step 3: Provide monitoring commands
echo -e "\n${BLUE}=== Monitoring Commands ===${NC}"
echo "Watch SLURM job status:"
echo "  squeue -u $USER"
echo ""
echo "Watch experiment progress:"
echo "  watch -n 10 'dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT status'"
echo ""
echo "Tail SLURM output:"
echo "  tail -f /scratch/ddr8143/repos/dr_exp/logs/dr_exp_${EXPERIMENT}_${SLURM_JOB_ID}.out"
echo ""
echo "Check worker logs:"
echo "  ls -la $BASE_PATH/$EXPERIMENT/logs/"
echo ""
echo "View completed jobs:"
echo "  dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT list --status completed"