#!/bin/bash
# Load environment
source /scratch/ddr8143/repos/dr_exp/.env
export SUPABASE_ANON_KEY=$SUPABASE_KEY

cd /scratch/ddr8143/repos/dr_exp

echo "Starting workers with Supabase sync enabled..."
echo "SUPABASE_URL: ${SUPABASE_URL:0:30}..."

# Start 2 workers
CUDA_VISIBLE_DEVICES=0 uv run dr_exp --base-path chronological_ablation --experiment main worker --worker-id gpu_worker_1 --max-jobs 2 &
sleep 5
CUDA_VISIBLE_DEVICES=0 uv run dr_exp --base-path chronological_ablation --experiment main worker --worker-id gpu_worker_2 --max-jobs 1 &

echo "Workers started. Monitoring..."
