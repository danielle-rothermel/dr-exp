#!/bin/bash
# Submit controlled experiments with fixed augmentation

echo "Submitting controlled experiments with fixed moderate augmentation..."
echo "Fixed augmentations: HFlip + ColorJitter + RRC (no mixup/cutmix/randaug)"
echo ""

# Base configuration (SGD, ResNet18, with residual, no dropout)
echo "1. Controlled base (SGD baseline)..."
python scripts/submit_jobs.py \
  --configs controlled_base \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,base" \
  --priority 250

# Optimizer comparison
echo "2. Controlled AdamW (optimizer comparison)..."
python scripts/submit_jobs.py \
  --configs controlled_adamw \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,optimizer" \
  --priority 240

# Architecture comparisons
echo "3. Controlled ResNet12 (architecture comparison)..."
python scripts/submit_jobs.py \
  --configs controlled_resnet12 \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,architecture" \
  --priority 230

echo "4. Controlled AlexNet (architecture comparison)..."
python scripts/submit_jobs.py \
  --configs controlled_alexnet \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,architecture" \
  --priority 220

# Architectural features
echo "5. Controlled No Residual (residual connection comparison)..."
python scripts/submit_jobs.py \
  --configs controlled_no_residual \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,residual" \
  --priority 210

# Learning rate schedule
echo "6. Controlled StepLR (scheduler comparison)..."
python scripts/submit_jobs.py \
  --configs controlled_steplr \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,scheduler" \
  --priority 200

# Regularization
echo "7. Controlled Dropout (regularization comparison)..."
python scripts/submit_jobs.py \
  --configs controlled_dropout \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,moderate-aug,regularization" \
  --priority 190

# Heavy augmentation comparison
echo "8. Controlled Heavy Aug (augmentation strength comparison)..."
python scripts/submit_jobs.py \
  --configs controlled_heavy_aug \
  --seeds 0 1 2 3 4 5 \
  --tags "controlled-exp,heavy-aug,comparison" \
  --priority 180

echo ""
echo "Controlled experiment submission complete!"
echo "Total: 8 configs × 6 seeds = 48 jobs"
echo ""
echo "Configs 1-7 use the same moderate augmentation:"
echo "- Random Resized Crop (scale 0.8-1.0)"
echo "- Horizontal Flip"  
echo "- ColorJitter (reduced: 0.1 for all params)"
echo "- NO mixup, cutmix, randaug, or label smoothing"
echo ""
echo "Config 8 uses heavy augmentation for comparison"