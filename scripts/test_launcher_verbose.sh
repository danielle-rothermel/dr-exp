#!/bin/bash
# Test launcher with verbose output and single worker

BASE_PATH="/scratch/ddr8143/repos/dr_exp/test_launcher"
EXPERIMENT="debug_test"

echo "=== Testing launcher with verbose output ==="

# Clean start
rm -rf "$BASE_PATH/$EXPERIMENT"

# Initialize
echo "1. Initializing experiment..."
uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT init

# Submit a simple test job
echo ""
echo "2. Submitting test job..."
uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT job submit \
    --config-path exp_configs \
    --config-name step00_baseline \
    --overrides "epochs=1 limit_train_batches=2 limit_val_batches=1" \
    --priority 100

# Check submission
echo ""
echo "3. Checking job queue..."
uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT list

# Try running a single worker directly first
echo ""
echo "4. Testing single worker directly..."
echo "Running worker for 30 seconds..."
timeout 30 uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT worker \
    --worker-id test_worker_$$ \
    --max-jobs 1 || true

# Check what happened
echo ""
echo "5. Checking results..."
uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT status

# Now try the launcher with debug output
echo ""
echo "6. Testing launcher with strace (first 100 lines)..."
timeout 10 strace -f -e trace=process -o /tmp/launcher_trace.txt \
    uv run dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT system launcher \
    --workers-per-gpu 1 --max-hours 1 2>&1 | head -100 || true

echo ""
echo "7. Checking what processes were created..."
grep -E "(fork|clone|exec)" /tmp/launcher_trace.txt | head -20 || true

# Alternative: run with Python debugging
echo ""
echo "8. Testing with Python verbose mode..."
timeout 10 python -v -m dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT system launcher \
    --workers-per-gpu 1 --max-hours 1 2>&1 | grep -E "(launcher|worker|spawn)" | head -20 || true