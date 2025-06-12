#!/bin/bash
# Test launcher in background to see what happens

BASE_PATH="/scratch/ddr8143/repos/dr_exp/test_background"
EXPERIMENT="test"

echo "=== Testing launcher in background ==="

# Clean start
rm -rf "$BASE_PATH/$EXPERIMENT"

# Initialize and submit test job
cd /scratch/ddr8143/repos/dr_exp
source .venv/bin/activate

echo "1. Initializing..."
dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT init

echo "2. Submitting test job..."
dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT job submit \
    --config-path exp_configs \
    --config-name step00_baseline \
    --overrides "epochs=1 limit_train_batches=2" \
    --priority 100

echo "3. Starting launcher in background..."
nohup dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT system launcher \
    --workers-per-gpu 1 --max-hours 0.1 \
    > "$BASE_PATH/$EXPERIMENT/launcher_output.log" 2>&1 &

LAUNCHER_PID=$!
echo "Launcher PID: $LAUNCHER_PID"

echo "4. Waiting 10 seconds..."
sleep 10

echo "5. Checking if launcher is still running..."
if ps -p $LAUNCHER_PID > /dev/null; then
    echo "✓ Launcher is running"
    echo "6. Checking for worker processes..."
    ps aux | grep -E "dr_exp.*worker" | grep -v grep
    
    echo "7. Checking logs..."
    echo "--- Launcher output ---"
    tail -20 "$BASE_PATH/$EXPERIMENT/launcher_output.log"
    
    echo ""
    echo "--- Worker logs ---"
    ls -la "$BASE_PATH/$EXPERIMENT/logs/"
    
    # Kill launcher
    echo "8. Stopping launcher..."
    kill $LAUNCHER_PID
else
    echo "✗ Launcher died"
    echo "Checking output:"
    cat "$BASE_PATH/$EXPERIMENT/launcher_output.log"
fi

echo ""
echo "9. Final status:"
dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT status