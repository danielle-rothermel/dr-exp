#!/bin/bash
# Submit SGD experiments with lower learning rate (0.05 instead of 0.1)

echo "Submitting SGD experiments with lower learning rate (lr=0.05)..."
export BASE_PATH=/scratch/ddr8143/logs/dcnn_workers
export EXPERIMENT=cluster_t0

# Step 01: SGD with all augmentations
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs step01_sgd \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 195

sleep 2

# Step 02: No RandAug
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs step02_no_randaug \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 185

sleep 2

# Step 03: No CutMix  
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs step03_no_cutmix \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 175

sleep 2

# Step 04: No Mixup
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs step04_no_mixup \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 165

sleep 2

# Step 05: No Warmup
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs step05_no_warmup \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 155

sleep 2

# Step 06: StepLR
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs step06_steplr \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 145

sleep 2

# Step 07: No Residual
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs step07_no_residual \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 135

sleep 2

# Skip steps 08-10 (LRN issues with xavier init)

# Step 11 (renumbered from original 14): Tanh
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs step14_tanh \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 125

sleep 2

# Step 12 (renumbered from original 15): No ColorJitter
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs step15_no_colorjitter \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 115

sleep 2

# Step 13 (renumbered from original 16): No RRC
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs step16_no_rrc \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 105

sleep 2

# Step 14 (renumbered from original 17): No HFlip
uv run python scripts/submit_jobs.py \
  --base-path ${BASE_PATH} --experiment ${EXPERIMENT} --experiment-type chrono \
  --configs step17_no_hflip \
  --seeds 0 1 2 3 4 5 \
  --overrides "optim.lr=0.05" \
  --tags "sgd-lr-sweep,lr-0.05" \
  --priority 95

echo "SGD lower learning rate sweep submission complete!"
echo "Submitted 11 configs × 6 seeds = 66 jobs"
echo "Skipped steps 8-10 (originally 11-13) as requested"
