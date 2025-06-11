# Chronological Deep Learning Experiments

This directory contains configuration files for a series of experiments that progressively remove modern deep learning techniques in chronological order, starting from a state-of-the-art configuration and working backwards to classical neural network approaches.

## Experiment Overview

Each configuration file builds upon the previous one, removing one modern technique at a time. The experiments are designed to study the impact of each innovation on CIFAR-10 classification performance.

## Configuration Files

### Step 00: Baseline (step00_baseline.yaml)
- **Full modern configuration** with all state-of-the-art techniques
- AdamW optimizer with weight decay
- Cosine annealing learning rate schedule
- 5 epochs of linear warmup
- Full augmentation suite: Horizontal flip, RRC (scale 0.7-1.0), Color Jitter, RandAugment, Mixup, CutMix
- ResNet18 architecture with CIFAR-10 optimizations (3x3 initial conv, no maxpool)
- Batch normalization
- ReLU activations
- He initialization
- Residual connections

### Step 01: SGD Optimizer (step01_sgd.yaml)
- **Remove**: AdamW optimizer
- **Replace with**: SGD with momentum

### Step 02: No RandAugment (step02_no_randaug.yaml)
- **Remove**: RandAugment (2019)

### Step 03: No CutMix (step03_no_cutmix.yaml)
- **Remove**: CutMix augmentation (2019)

### Step 04: No Mixup (step04_no_mixup.yaml)
- **Remove**: Mixup augmentation (2018)

### Step 05: No Warmup (step05_no_warmup.yaml)
- **Remove**: Learning rate warmup

### Step 06: Step LR Decay (step06_steplr.yaml)
- **Remove**: Cosine annealing
- **Replace with**: Step-based learning rate decay

### Step 07: No Residual Connections (step07_no_residual.yaml)
- **Remove**: Residual/skip connections
- **Result**: "PlainNet18" - same architecture but without shortcuts

### Step 08: LRN + Dropout (step08_lrn_dropout.yaml)
- **Remove**: Batch Normalization
- **Replace with**: Local Response Normalization (LRN) + Dropout (0.4)

### Step 09: Xavier Initialization (step09_xavier.yaml)
- **Remove**: He initialization
- **Replace with**: Xavier/Glorot initialization

### Step 10: No LRN (step10_no_lrn.yaml)
- **Remove**: Local Response Normalization
- **Keep**: Only dropout for regularization

### Step 11: ResNet12 (step11_resnet12.yaml)
- **Reduce**: From 18 to 12 layers

### Step 12: AlexNet-style (step12_alexnet.yaml)
- **Reduce**: To 8 layers (5 convolutional + 3 fully connected)
- **Architecture**: AlexNet-style network

### Step 13: No Dropout (step13_no_dropout.yaml)
- **Remove**: Dropout regularization

### Step 14: Tanh Activation (step14_tanh.yaml)
- **Remove**: ReLU activation
- **Replace with**: Tanh activation

### Step 15: No Color Jitter (step15_no_colorjitter.yaml)
- **Remove**: Color Jitter augmentation

### Step 16: No RRC (step16_no_rrc.yaml)
- **Remove**: Random Resized Crop augmentation

### Step 17: No Horizontal Flip (step17_no_hflip.yaml)
- **Remove**: Horizontal flip augmentation
- **Result**: No data augmentation, classical neural network

## Running Experiments

To run any experiment configuration:

```bash
# Run with a specific configuration
uv run python scripts/train_cnn.py --config-name exp_configs/step00_baseline.yaml

# Run with multiple seeds (recommended)
for seed in 0 1 2; do
    uv run python scripts/train_cnn.py --config-name exp_configs/step00_baseline.yaml seed=$seed
done

# Run with limited batches for testing
uv run python scripts/train_cnn.py --config-name exp_configs/step00_baseline.yaml limit_train_batches=10

# Run on Mac with reduced epochs for testing
uv run python scripts/train_cnn.py --config-name exp_configs/step00_baseline.yaml machine=mac epochs=1
```

## Expected Results

As you progress through the steps, you should observe:
1. Gradual degradation in model performance
2. Increased training instability in later steps
3. Potentially slower convergence
4. Lower final accuracy on CIFAR-10

## Notes

- Each configuration inherits from the previous step, creating a cumulative removal of features
- The experiment design follows the chronological introduction of these techniques in the deep learning literature
- All configurations maintain the same base training setup (batch size, number of epochs, etc.) unless specifically modified