# deconCNN Integration with dr_exp: Implementation Guide

## Overview

This document provides complete context for integrating the **deconCNN** deep learning library with the **dr_exp** distributed job scheduler. The goal is to enable experimental sweeps using deconCNN models through dr_exp's job management system, ultimately targeting real Slurm clusters.

## Current Status

### ✅ **Completed Work**

1. **Clean Config Interface**: Implemented proper separation between job management and training configs
   - Worker now unwraps training configs before passing to training functions
   - Training functions receive native config format (not dr_exp's internal structure)
   - 97.9% test success rate (93/95 tests passing)

2. **Basic Integration Infrastructure**: 
   - Added deconCNN as dependency in `pyproject.toml`
   - Created Hydra configuration structure for deconCNN testing
   - Implemented test utilities for wrapped config format

3. **Progressive Testing Plan**: Established strategy for local → remote DB → GPU → Slurm testing

### 🚧 **Next Phase: Training Function Integration**

The immediate goal is to create a deconCNN training function that works with dr_exp's interface.

## System Architecture

### dr_exp Configuration Flow

```
Config Upload → JobDB Storage → Worker Retrieval → Training Function
     ↓               ↓               ↓                    ↓
Hydra YAML    {"config": {...},  training_config    Native config
   +          "metadata": {...}}     ↓               for training
Sweep params                    cfg["config"]        function
```

### Key Interface Requirements

**Training Function Signature:**
```python
def train(cfg: Any, logger: Optional[BaseLogger] = None) -> Dict[str, Any]:
    """
    Args:
        cfg: Training configuration (unwrapped, native format)
        logger: dr_exp's StructuredLogger for metrics/checkpoints
    
    Returns:
        Dict with required keys: "status", "final_val_acc", "final_train_loss", etc.
    """
```

## deconCNN Library Analysis

### Key Components Available

From `deconcnn` package:
- **`create_cifar10_training_components(cfg)`**: Returns `(model, data_module, trainer)` 
- **`train_model(trainer, model, data_module, cfg)`**: Runs training loop
- **`ClassificationModule`**: Lightning module with metrics logging
- **`create_model(architecture, **kwargs)`**: Model factory
- **Config format**: Expects flat OmegaConf structure

### deconCNN Config Structure

```yaml
# Expected by deconCNN
epochs: 2
batch_size: 32
model:
  name: "alexnet_cifar"
  architecture: "CifarAlexNet"
  # ... model params
optim:
  name: "adamw"
  lr: 0.01
data:
  name: "cifar10"
  num_workers: 2
# ... flat structure
```

## Implementation Tasks

### 1. **Create deconCNN Training Function**

**Location**: `src/dr_exp/train_examples/decon_trainer.py`

**Requirements**:
- Convert dr_exp config format to deconCNN's expected OmegaConf structure
- Route deconCNN metrics through dr_exp's StructuredLogger
- Handle checkpoints via dr_exp's checkpoint system
- Return standardized results dictionary

**Template**:
```python
def train_with_decon(cfg: Any, logger: Optional[BaseLogger] = None) -> Dict[str, Any]:
    """Training function integrating deconCNN with dr_exp."""
    
    # 1. Convert config format
    decon_cfg = convert_dr_exp_to_decon_config(cfg)
    
    # 2. Setup logging integration
    if logger is None:
        logger = StructuredLogger("./logs")
    
    # 3. Create components using deconCNN
    model, data_module, trainer = create_cifar10_training_components(decon_cfg)
    
    # 4. Integrate logging (key challenge)
    # Need to route Lightning metrics → dr_exp logger
    
    # 5. Run training
    train_model(trainer, model, data_module, decon_cfg)
    
    # 6. Extract and return results
    return {
        "status": "success",
        "final_val_acc": extract_final_val_acc(),
        "final_train_loss": extract_final_train_loss(),
        # ... other required fields
    }
```

### 2. **Logging Integration Challenge**

**Problem**: deconCNN uses Lightning's logging, dr_exp uses StructuredLogger

**Solutions to explore**:

1. **Lightning Logger Adapter**: Create custom Lightning logger that forwards to StructuredLogger
2. **Metrics Extraction**: Parse Lightning's logged metrics and forward to dr_exp
3. **Callback Integration**: Use Lightning callbacks to capture metrics

### 3. **Configuration Translation**

**Challenge**: Convert between config formats

```python
def convert_dr_exp_to_decon_config(dr_exp_cfg):
    """Convert dr_exp config to deconCNN OmegaConf format."""
    return OmegaConf.create({
        "epochs": dr_exp_cfg.get("epochs", 2),
        "batch_size": dr_exp_cfg.get("batch_size", 32),
        "model": dr_exp_cfg.get("model", default_model_config),
        # ... handle all required fields
    })
```

### 4. **Testing Workflow**

**Phase 1: Local Development**
```bash
# Test config upload
uv run python scripts/upload_configs.py \
  --base-config-path src/dr_exp/train_examples/configs \
  --config-name decon_integration_config \
  --sweep "model.name=alexnet_cifar epochs=2,3" \
  --priority 150

# Test worker execution  
EXPMGR_MODE="files_local" uv run python scripts/run_worker.py
```

**Phase 2: Database Testing**
- Local files: `EXPMGR_MODE="files_local"`
- Local Supabase: `EXPMGR_MODE="supabase_local"` (requires Docker)
- Remote Supabase: `EXPMGR_MODE="supabase_remote"` (requires cloud setup)

**Phase 3: GPU Testing**
- Interactive GPU shell testing
- Verify CUDA/PyTorch compatibility
- Test model training on actual hardware

**Phase 4: Slurm Integration**
- Test job submission from CPU nodes
- Verify GPU resource allocation
- Run experimental sweeps

## Existing Configuration Files

### Available Configs

**Main configs**: `src/dr_exp/train_examples/configs/`
- `decon_integration_config.yaml`: Basic integration test config
- `decon_test_config.yaml`: ResNet12 model config  
- `decon_alexnet_config.yaml`: AlexNet model config

**Component configs**:
- `model/`: `alexnet_cifar.yaml`, `resnet12_cifar.yaml`
- `machine/mac.yaml`: Local development setup
- `optim/adamw.yaml`: Optimizer configuration
- `lrsched/cosine.yaml`: Learning rate scheduler
- `train_transforms/minimal.yaml`: Fast training transforms

### Example Usage

```bash
# Quick local test
uv run python scripts/upload_configs.py \
  --config-name decon_integration_config \
  --sweep "epochs=1,2 batch_size=16,32"

# Multi-model comparison
uv run python scripts/upload_configs.py \
  --config-name decon_integration_config \
  --sweep "model.name=alexnet_cifar,resnet12_cifar epochs=5"
```

## Technical Challenges & Solutions

### 1. **Metrics Logging Integration**

**Challenge**: Two different logging systems
- deconCNN: Lightning's built-in logging (CSV, TensorBoard)
- dr_exp: StructuredLogger (JSONL metrics, checkpoint management)

**Approach**: Create adapter layer that routes Lightning metrics through StructuredLogger

### 2. **Checkpoint Management**

**Challenge**: Lightning vs dr_exp checkpoint formats
- Lightning: Automatic best/last model saving
- dr_exp: Explicit checkpoint calls with metadata

**Approach**: Extract Lightning checkpoints and save via dr_exp's system

### 3. **Error Handling**

**Challenge**: Different error reporting mechanisms
- Lightning: Exception handling in training loop
- dr_exp: Structured error reporting with status codes

**Approach**: Wrap deconCNN calls with proper exception handling

### 4. **Resource Management**

**Challenge**: GPU memory and process management
- deconCNN: May expect dedicated GPU access
- dr_exp: Multiple jobs per GPU possible

**Approach**: Careful resource allocation and cleanup

## Development Environment Setup

### Required Dependencies

Already available:
- `deconCNN` (via git dependency)
- `lightning` (PyTorch Lightning)
- `hydra-core` (configuration management)
- `torch`, `torchvision` (deep learning)

### Environment Variables

```bash
# Local testing
export EXPMGR_MODE="files_local"
export DR_EXP_BASE_PATH="/tmp/dr_exp_test"

# GPU testing  
export CUDA_VISIBLE_DEVICES="0"  # Single GPU

# Supabase testing
export EXPMGR_MODE="supabase_local"
# Requires: supabase start (Docker)
```

## Debugging & Validation

### Test Commands

```bash
# Verify deconCNN import
uv run python -c "import deconcnn; print('OK')"

# Test config loading
uv run python -c "
from hydra import compose, initialize_config_dir
with initialize_config_dir('src/dr_exp/train_examples/configs'):
    cfg = compose('decon_integration_config')
    print(cfg.model.name)
"

# Test training function (once implemented)
uv run python -c "
from dr_exp.train_examples.decon_trainer import train_with_decon
from dr_exp.logging.structured_logger import StructuredLogger
cfg = {'epochs': 1, 'model': {'name': 'alexnet_cifar'}}
logger = StructuredLogger('/tmp/test_logs')
result = train_with_decon(cfg, logger)
print(result)
"
```

### Expected Outputs

**Successful training result**:
```python
{
    "status": "success",
    "final_val_acc": 0.85,
    "final_train_loss": 0.45,
    "num_epochs": 2,
    "model_name": "alexnet_cifar",
    "metrics_path": "/path/to/metrics.jsonl",
    "artifacts_path": "/path/to/artifacts/",
    "num_checkpoints": 1
}
```

## Production Deployment Considerations

### Slurm Integration

**Job submission workflow**:
1. Upload configs from login node
2. Submit worker jobs to GPU partition
3. Workers claim jobs and execute training
4. Results aggregated in shared storage

**Resource allocation**:
```bash
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
```

### Data Management

**Considerations**:
- CIFAR-10 download location (shared vs local storage)
- Checkpoint storage (network filesystem)
- Metrics aggregation across jobs

### Monitoring

**Key metrics to track**:
- Job completion rates
- Training convergence
- Resource utilization
- Error patterns

## Next Steps for Implementation

### Immediate Tasks (Priority 1)

1. **Create `decon_trainer.py`** with basic training function
2. **Implement config conversion** between dr_exp and deconCNN formats
3. **Test basic integration** with simple CIFAR-10 training

### Short-term Goals (Priority 2)

4. **Implement logging integration** (Lightning → StructuredLogger)
5. **Add checkpoint management** via dr_exp system
6. **Test with multiple models** (AlexNet, ResNet12)

### Medium-term Goals (Priority 3)

7. **GPU testing** on interactive nodes
8. **Slurm integration** testing
9. **Production experimental sweeps**

This guide provides the complete context needed to continue the deconCNN integration work. The foundation is solid, and the remaining work focuses on bridging the logging and execution interfaces between the two systems.