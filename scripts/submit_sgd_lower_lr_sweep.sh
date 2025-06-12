#!/bin/bash
# Submit SGD experiments with lower learning rate (0.05 instead of 0.1)

echo "Submitting SGD experiments with lower learning rate (lr=0.05)..."

# Step 01: SGD with all augmentations
python scripts/submit_jobs.py \
  --configs step01_sgd \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 195

# Step 02: No RandAug
python scripts/submit_jobs.py \
  --configs step02_no_randaug \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 185

# Step 03: No CutMix  
python scripts/submit_jobs.py \
  --configs step03_no_cutmix \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 175

# Step 04: No Mixup
python scripts/submit_jobs.py \
  --configs step04_no_mixup \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 165

# Step 05: No Warmup
python scripts/submit_jobs.py \
  --configs step05_no_warmup \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 155

# Step 06: StepLR
python scripts/submit_jobs.py \
  --configs step06_steplr \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 145

# Step 07: No Residual
python scripts/submit_jobs.py \
  --configs step07_no_residual \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 135

# Skip steps 08-10 (LRN issues with xavier init)

# Step 11 (renumbered from original 14): Tanh
python scripts/submit_jobs.py \
  --configs step14_tanh \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 125

# Step 12 (renumbered from original 15): No ColorJitter
python scripts/submit_jobs.py \
  --configs step15_no_colorjitter \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 115

# Step 13 (renumbered from original 16): No RRC
python scripts/submit_jobs.py \
  --configs step16_no_rrc \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 105

# Step 14 (renumbered from original 17): No HFlip
python scripts/submit_jobs.py \
  --configs step17_no_hflip \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 95

echo "SGD lower learning rate sweep submission complete!"
echo "Submitted 11 configs × 6 seeds = 66 jobs"
echo "Skipped steps 8-10 (originally 11-13) as requested"