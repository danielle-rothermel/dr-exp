#!/bin/bash
# Submit controlled experiments with fixed augmentation

echo "Submitting controlled experiments with fixed moderate augmentation..."
echo "Fixed augmentations: HFlip + ColorJitter + RRC (no mixup/cutmix/randaug)"
echo ""
export BASE_PATH=/scratch/ddr8143/logs/dcnn_workers
export EXPERIMENT=cluster_t0

# Base configuration (SGD, ResNet18, with residual, no dropout)
echo "1. Controlled base (SGD baseline)..."
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs controlled_base \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,base" \
  --priority 250

sleep 2

# Optimizer comparison
echo "2. Controlled AdamW (optimizer comparison)..."
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs controlled_adamw \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,optimizer" \
  --priority 240

sleep 2

# Architecture comparisons
echo "3. Controlled ResNet12 (architecture comparison)..."
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs controlled_resnet12 \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,architecture" \
  --priority 230

sleep 2

echo "4. Controlled AlexNet (architecture comparison)..."
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs controlled_alexnet \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,architecture" \
  --priority 220

sleep 2

# Architectural features
echo "5. Controlled No Residual (residual connection comparison)..."
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs controlled_no_residual \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,residual" \
  --priority 210

sleep 2

# Learning rate schedule
echo "6. Controlled StepLR (scheduler comparison)..."
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs controlled_steplr \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,scheduler" \
  --priority 200

sleep 2

# Regularization
echo "7. Controlled Dropout (regularization comparison)..."
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs controlled_dropout \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,regularization" \
  --priority 190

echo ""
echo "Controlled experiment submission complete!"
echo "Total: 8 configs × 6 seeds = 48 jobs (skipped num 8)"
echo ""
echo "Configs 1-7 use the same moderate augmentation:"
echo "- Random Resized Crop (scale 0.8-1.0)"
echo "- Horizontal Flip"  
echo "- ColorJitter (reduced: 0.1 for all params)"
echo "- NO mixup, cutmix, randaug, or label smoothing"
echo ""
