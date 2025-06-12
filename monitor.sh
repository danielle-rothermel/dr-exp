#!/bin/bash
cd /scratch/ddr8143/repos/dr_exp
while true; do
    clear
    echo "=== Experiment Monitor - $(date) ==="
    echo
    uv run dr_exp --base-path chronological_ablation --experiment main status
    echo
    echo "=== GPU Status ==="
    nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv
    echo
    echo "=== Active Workers ==="
    ps aux | grep -E "dr_exp.*worker" | grep -v grep | awk '{print $2, $11, $12, $13, $14}'
    echo
    echo "=== Recent Jobs ==="
    uv run dr_exp --base-path chronological_ablation --experiment main job list --status running | head -10
    sleep 15
done