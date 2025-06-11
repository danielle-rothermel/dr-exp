#!/bin/bash
# Launch 4 workers for high regularization experiment

export EXP_DIR=/scratch/ddr8143/repos/dr_exp/high_regularization_ablation

echo "=== Launching 4 Workers for High Regularization Experiment ==="
echo "Experiment directory: $EXP_DIR"
echo "Workers: 4"
echo ""

# Create work directories
for i in {0..3}; do
    mkdir -p $EXP_DIR/work_$i
done

# Launch 4 workers
for i in {0..3}; do
    echo "Starting worker_$i..."
    nohup uv run dr_exp --base-path $EXP_DIR --experiment main worker \
        --worker-id worker_$i \
        --working-dir $EXP_DIR/work_$i > $EXP_DIR/worker_$i.log 2>&1 &
    echo "  PID: $!"
    sleep 1  # Small delay between launches
done

echo ""
echo "All workers launched!"
echo ""
echo "To monitor workers:"
echo "  tail -f $EXP_DIR/worker_*.log"
echo ""
echo "To check running workers:"
echo "  ps aux | grep 'worker_' | grep -v grep"
echo ""
echo "To stop all workers:"
echo "  pkill -f 'dr_exp.*worker.*high_regularization_ablation'"