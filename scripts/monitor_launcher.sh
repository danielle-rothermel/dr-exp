#!/bin/bash
# Monitor launcher and workers in real-time

BASE_PATH=${1:-/scratch/ddr8143/repos/dr_exp/chronological_ablation}
EXPERIMENT=${2:-main}

echo "Monitoring experiment: $EXPERIMENT"
echo "Base path: $BASE_PATH"
echo "Press Ctrl+C to exit"
echo ""

# Function to show status
show_status() {
    clear
    echo "=== DR_EXP Monitor - $(date) ==="
    echo ""
    
    # Job status
    echo "JOB STATUS:"
    uv run dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" status 2>/dev/null | grep -E "(queued|running|completed|failed|Total)" || echo "  Unable to get status"
    echo ""
    
    # Worker processes
    echo "WORKER PROCESSES:"
    ps aux | grep -E "dr_exp.*worker" | grep -v grep | awk '{printf "  PID: %6s | CPU: %3s%% | MEM: %3s%% | %s\n", $2, $3, $4, substr($0, index($0,$11))}'
    WORKER_COUNT=$(ps aux | grep -E "dr_exp.*worker" | grep -v grep | wc -l)
    echo "  Total workers: $WORKER_COUNT"
    echo ""
    
    # Latest logs
    if [ -d "$BASE_PATH/$EXPERIMENT/logs" ]; then
        echo "LATEST LOG ACTIVITY:"
        # Find most recent log files
        RECENT_LOGS=$(find "$BASE_PATH/$EXPERIMENT/logs" -name "*.log" -type f -mmin -5 2>/dev/null | sort -r | head -5)
        if [ -n "$RECENT_LOGS" ]; then
            for log in $RECENT_LOGS; do
                echo "  $(basename $log): $(tail -1 $log 2>/dev/null | cut -c1-80)"
            done
        else
            echo "  No recent log activity"
        fi
    fi
    echo ""
    
    # Control files
    if [ -d "$BASE_PATH/$EXPERIMENT/control" ]; then
        echo "CONTROL FILES:"
        ls -la "$BASE_PATH/$EXPERIMENT/control/" 2>/dev/null | tail -n +2 | awk '{print "  " $9}'
    fi
    echo ""
    
    # GPU usage
    echo "GPU USAGE:"
    nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used --format=csv,noheader,nounits | \
        awk -F', ' '{printf "  GPU %s: %s | Util: %3d%% | Mem: %5d MB\n", $1, $2, $3, $4}'
}

# Main loop
while true; do
    show_status
    sleep 5
done