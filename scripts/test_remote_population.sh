#!/bin/bash
# Test script to populate remote database with sample data

set -e  # Exit on error

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

echo "🚀 Testing Remote Database Population"
echo "===================================="

# Configuration
BASE_PATH="./test_remote_exp"
EXPERIMENT="remote_demo"
CONFIG_DIR="./test_configs"

# Step 1: Clean up any existing test
echo -e "\n1️⃣ Cleaning up previous test..."
rm -rf "$BASE_PATH/$EXPERIMENT"
rm -rf work/test_worker_*

# Step 2: Initialize experiment
echo -e "\n2️⃣ Initializing experiment..."
uv run dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" init

# Step 3: Create test config
echo -e "\n3️⃣ Creating test configuration..."
mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_DIR/test_trainer.yaml" << 'EOF'
_target_: dr_exp.trainers.test_trainer.train

# Quick test - runs fast
epochs: 1
batch_size: 16
steps_per_epoch: 5

# Generate some output files
save_checkpoint: true
save_metrics: true
log_interval: 1

# Model config
model:
  name: test_model
  hidden_size: 64
EOF

# Step 4: Submit multiple jobs
echo -e "\n4️⃣ Submitting test jobs..."
echo "   High priority job..."
uv run dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" job submit \
  --config-path "$CONFIG_DIR" --config-name test_trainer --priority 900

echo "   Normal priority job..."
uv run dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" job submit \
  --config-path "$CONFIG_DIR" --config-name test_trainer --priority 100 \
  --overrides "model.hidden_size=128"

echo "   Low priority job..."
uv run dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" job submit \
  --config-path "$CONFIG_DIR" --config-name test_trainer --priority 10 \
  --overrides "epochs=2"

# Step 5: List local jobs
echo -e "\n5️⃣ Local jobs created:"
uv run dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" job list

# Step 6: Check remote before running worker
echo -e "\n6️⃣ Checking remote database (before worker)..."
uv run python scripts/check_remote_db.py

# Step 7: Run worker with sync enabled
echo -e "\n7️⃣ Running worker with sync enabled..."
echo "   This will populate the remote database!"
echo "   Press Ctrl+C after jobs complete (watch for 'Worker completed' message)"
echo ""
uv run dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT" worker \
  --worker-id test_worker_01 \
  --working-dir ./work/test_worker_01 \
  --max-jobs 3

# Step 8: Final check
echo -e "\n8️⃣ Checking remote database (after worker)..."
uv run python scripts/check_remote_db.py

echo -e "\n✅ Test complete!"
echo "Check your Supabase dashboard at:"
echo "https://supabase.com/dashboard/project/yfawygsfsuwrqvohsayp/editor"