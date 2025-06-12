#!/bin/bash
# Debug script to see what's happening with the launcher

BASE_PATH=${BASE_PATH:-/scratch/ddr8143/repos/dr_exp/chronological_ablation}
EXPERIMENT=${EXPERIMENT:-main}

echo "=== Debugging dr_exp launcher ==="
echo "Base path: $BASE_PATH"
echo "Experiment: $EXPERIMENT"
echo ""

# Check if experiment exists
if [ ! -d "$BASE_PATH/$EXPERIMENT" ]; then
    echo "ERROR: Experiment directory doesn't exist!"
    echo "Run: dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT init"
    exit 1
fi

# Check job status
echo "=== Current Job Status ==="
uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT status

# Check for any existing worker processes
echo ""
echo "=== Existing dr_exp processes ==="
ps aux | grep -E "(dr_exp|worker)" | grep -v grep

# Check logs directory
echo ""
echo "=== Log files ==="
if [ -d "$BASE_PATH/$EXPERIMENT/logs" ]; then
    echo "Recent logs:"
    ls -la "$BASE_PATH/$EXPERIMENT/logs/" | tail -10
    
    # Check for launcher log
    if [ -f "$BASE_PATH/$EXPERIMENT/logs/launcher.log" ]; then
        echo ""
        echo "=== Last 20 lines of launcher.log ==="
        tail -20 "$BASE_PATH/$EXPERIMENT/logs/launcher.log"
    fi
    
    # Check for recent worker logs
    echo ""
    echo "=== Recent worker logs ==="
    LATEST_WORKER_LOG=$(ls -t "$BASE_PATH/$EXPERIMENT/logs/worker_"*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_WORKER_LOG" ]; then
        echo "Latest worker log: $LATEST_WORKER_LOG"
        tail -10 "$LATEST_WORKER_LOG"
    else
        echo "No worker logs found"
    fi
fi

# Check control directory
echo ""
echo "=== Control files ==="
if [ -d "$BASE_PATH/$EXPERIMENT/control" ]; then
    ls -la "$BASE_PATH/$EXPERIMENT/control/"
fi

# GPU status
echo ""
echo "=== GPU Status ==="
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv

# Check if jobs are queued
echo ""
echo "=== Queued Jobs ==="
QUEUED_COUNT=$(uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT job list --status queued | grep -c "queued" || echo 0)
echo "Queued jobs: $QUEUED_COUNT"

if [ "$QUEUED_COUNT" -eq 0 ]; then
    echo "WARNING: No queued jobs! Workers will have nothing to do."
fi
