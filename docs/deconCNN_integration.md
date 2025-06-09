# deconCNN Integration with dr_exp

This document describes how to use deconCNN (deep learning library) with dr_exp's distributed job scheduling system.

## Architecture Overview

The integration follows a clean separation between upload-time config composition and worker-time training execution:

1. **Upload Step**: Use Hydra to compose complete deconCNN configs and upload to JobDB
2. **Worker Step**: Claim jobs and run training with pre-composed configs

## Quick Start

### Prerequisites

```bash
# Install dependencies
uv sync

# Set environment variables for local testing
export EXPMGR_MODE="files_local"
export DR_EXP_BASE_PATH="/Users/daniellerothermel/drotherm/repos/dr_exp/experiment_data"
```

### Upload deconCNN Training Jobs

```bash
# Basic upload with default settings
uv run python scripts/upload_configs.py \
  --base-config-path=deconcnn_configs \
  --config-name=config \
  --sweep="epochs=10 machine=mac" \
  --description="deconCNN training run" \
  --priority=200

# Multi-model sweep
uv run python scripts/upload_configs.py \
  --base-config-path=deconcnn_configs \
  --config-name=config \
  --sweep="model=resnet18_cifar,resnet12_cifar epochs=10,20 machine=mac" \
  --description="Model comparison sweep" \
  --priority=300

# Custom hyperparameters
uv run python scripts/upload_configs.py \
  --base-config-path=deconcnn_configs \
  --config-name=config \
  --sweep="model=resnet18_cifar epochs=50 batch_size=64,128 optim.lr=0.001,0.01 machine=mac" \
  --description="Hyperparameter sweep" \
  --priority=400
```

### Run Training (Worker Simulation)

```bash
# Start a worker to claim and run jobs
uv run python scripts/run_worker.py

# Or test training manually with a specific job
uv run python -c "
import os
os.environ['EXPMGR_MODE'] = 'files_local'
os.environ['DR_EXP_BASE_PATH'] = os.path.join(os.getcwd(), 'experiment_data')

from src.dr_exp.utils.jobdb_factory import get_job_db_client
from src.dr_exp.train_examples.decon_trainer import train_with_decon

job_db = get_job_db_client()
jobs = job_db.list_jobs()
if jobs:
    config = jobs[0]['config_json']['config']
    result = train_with_decon(config)
    print(f'Status: {result.status}')
"
```

## Configuration Options

### Available Models

- `resnet18_cifar` - ResNet-18 optimized for CIFAR-10
- `resnet12_cifar` - ResNet-12 optimized for CIFAR-10  
- `alexnet_cifar` - AlexNet optimized for CIFAR-10

### Machine Configurations

- `machine=mac` - Use MPS (Metal Performance Shaders) on macOS
- `machine=cluster` - Use CUDA for cluster/GPU environments

### Common Sweep Parameters

```bash
# Model architecture
model=resnet18_cifar,resnet12_cifar,alexnet_cifar

# Training length
epochs=10,20,50,100

# Optimization
batch_size=32,64,128
optim.lr=0.001,0.01,0.1
optim.weight_decay=1e-4,1e-5

# Learning rate scheduling
lrsched=timm_cosine,torchvision_step

# Hardware
machine=mac,cluster
```

## Environment Variables

| Variable | Values | Description |
|----------|--------|-------------|
| `EXPMGR_MODE` | `files_local`, `supabase_local`, `supabase_remote` | Database backend |
| `DR_EXP_BASE_PATH` | Path | Base directory for job data storage |
| `ADMIN_API_KEY` | String | API key for admin endpoints (default: "testkey") |

## Example Workflows

### Local Development

```bash
# Set environment
export EXPMGR_MODE="files_local"
export DR_EXP_BASE_PATH="$(pwd)/experiment_data"

# Upload a quick test job
uv run python scripts/upload_configs.py \
  --base-config-path=deconcnn_configs \
  --config-name=config \
  --sweep="epochs=2 machine=mac" \
  --description="Quick test"

# Run training
uv run python scripts/run_worker.py
```

### Production Cluster

```bash
# Set environment for Supabase
export EXPMGR_MODE="supabase_remote"
export SUPABASE_URL="your-supabase-url"
export SUPABASE_KEY="your-supabase-key"

# Upload production jobs
uv run python scripts/upload_configs.py \
  --base-config-path=deconcnn_configs \
  --config-name=config \
  --sweep="model=resnet18_cifar epochs=100 batch_size=64 machine=cluster" \
  --description="Production training run" \
  --priority=500

# Deploy workers
uv run python scripts/run_worker.py
```

## Troubleshooting

### Device Issues

**Problem**: `CUDAAccelerator` cannot run on macOS
**Solution**: Use `machine=mac` in your sweep to enable MPS acceleration

```bash
# Correct for macOS
--sweep="model=resnet18_cifar epochs=10 machine=mac"

# Correct for CUDA clusters  
--sweep="model=resnet18_cifar epochs=10 machine=cluster"
```

### Upload Issues

**Problem**: Jobs appear to be created but don't show up in database
**Solution**: Ensure environment variables are set before running upload script

```bash
# Set these BEFORE running upload
export EXPMGR_MODE="files_local"
export DR_EXP_BASE_PATH="$(pwd)/experiment_data"

uv run python scripts/upload_configs.py ...
```

### Model Configuration

**Problem**: `Invalid architecture` errors
**Solution**: Use the exact model names from the available configs:

- ✅ `model=resnet18_cifar` 
- ✅ `model=resnet12_cifar`
- ✅ `model=alexnet_cifar`
- ❌ `model=resnet18` (missing `_cifar` suffix)

## Implementation Details

### Config Composition

The system uses Hydra to compose complete configurations during upload:

1. Base config from `deconcnn_configs/config.yaml`
2. Component configs from `deconcnn_configs/{model,optim,machine,etc}/`
3. User overrides from `--sweep` parameter
4. Validation using deconCNN's built-in validators

### Training Execution

Workers receive complete, validated configs and run training directly:

1. No Hydra composition needed on workers
2. Lightning module wrapper captures metrics in real-time
3. Results returned via standardized `TrainingResult` interface

### Metrics Logging

The integration provides both:
- **Real-time logging**: Epoch-by-epoch metrics to StructuredLogger
- **Final results**: Complete training metrics in standardized format
- **Deduplication**: Prevents duplicate logging during Lightning's multiple validation calls