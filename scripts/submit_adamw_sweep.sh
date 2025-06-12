#!/bin/bash
# Submit AdamW hyperparameter sweep for step00_baseline

echo "Submitting AdamW hyperparameter sweep..."

# Test 1: lr=0.003, wd=0.01 (3x higher LR, same WD)
python scripts/submit_jobs.py \
  --configs step00_baseline \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.003,optim.weight_decay=0.01" \
  --tags "adamw-sweep,lr-0.003,wd-0.01" \
  --priority 200

# Test 2: lr=0.003, wd=0.001 (3x higher LR, 10x lower WD)
python scripts/submit_jobs.py \
  --configs step00_baseline \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.003,optim.weight_decay=0.001" \
  --tags "adamw-sweep,lr-0.003,wd-0.001" \
  --priority 190

# Test 3: lr=0.005, wd=0.001 (5x higher LR, 10x lower WD)
python scripts/submit_jobs.py \
  --configs step00_baseline \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.005,optim.weight_decay=0.001" \
  --tags "adamw-sweep,lr-0.005,wd-0.001" \
  --priority 180

# Test 4: lr=0.002, wd=0.0005 (2x higher LR, match SGD's WD)
python scripts/submit_jobs.py \
  --configs step00_baseline \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.002,optim.weight_decay=0.0005" \
  --tags "adamw-sweep,lr-0.002,wd-0.0005" \
  --priority 170

echo "Sweep submission complete!"