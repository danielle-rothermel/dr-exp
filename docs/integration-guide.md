# dr_exp and deconCNN Integration Guide

## Overview

This document describes the integration between `dr_exp` (experiment manager) and `deconCNN` (deep learning framework). The integration allows distributed training jobs to be managed through a file-based queue system with automatic metric tracking and cloud synchronization.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         dr_exp                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│  │   CLI    │  │  JobDB   │  │  Worker  │  │ SyncHandler │ │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────────────┘ │
│        │             │              │                        │
│        └─────────────┴──────────────┘                       │
│                      │                                       │
│                      │ Hydra call with config               │
│                      ▼                                       │
│         ┌────────────────────────┐                         │
│         │ decon_trainer.train_   │                         │
│         │ classification()       │                         │
│         └───────────┬────────────┘                         │
└─────────────────────┼───────────────────────────────────────┘
                      │
┌─────────────────────┼───────────────────────────────────────┐
│    deconCNN         ▼                                       │
│  ┌──────────┐  ┌──────────┐  ┌─────────────┐              │
│  │ Factory  │  │  Model   │  │ DataModule  │              │
│  └──────────┘  └──────────┘  └─────────────┘              │
│                                                             │
│  ┌────────────────────────────┐                           │
│  │ DrExpMetricsCallback       │ ◄── Implements Protocol    │
│  └────────────────────────────┘                           │
└─────────────────────────────────────────────────────────────┘
```

## Configuration System

### 1. Hydra Configuration Composition

Both repositories use Hydra for configuration management, enabling hierarchical config composition:

#### dr_exp Job Config Example (`exp_configs/step00_baseline.yaml`):
```yaml
# @package _global_
_target_: "dr_exp.trainers.decon_trainer.train_classification"

defaults:
  - config  # Base deconCNN config
  - override /model: resnet18_cifar
  - override /optimizer: sgd
  - override /lr_scheduler: step
  - override /transforms: cifar10_baseline
  - override /machine: local
  - override /paths: local
  - _self_

data:
  dataset: cifar10
  batch_size: 128
  num_workers: 4

trainer:
  max_epochs: 100
  accelerator: gpu
  devices: 1
```

#### deconCNN Base Config (`configs/config.yaml`):
```yaml
defaults:
  - model: resnet18_cifar
  - optimizer: sgd
  - lr_scheduler: step
  - transforms: cifar10_baseline
  - _self_

data:
  dataset: cifar10
  batch_size: 128
  num_workers: 4
  persistent_workers: true
  pin_memory: true

trainer:
  max_epochs: 100
  accelerator: gpu
  devices: 1
  precision: 16-mixed
  gradient_clip_val: 1.0
```

### 2. Key Configuration Differences

- **dr_exp configs**: Must include `_target_` field pointing to the callable function
- **deconCNN configs**: Standalone configs without `_target_` for direct usage
- **Shared structure**: Both use identical hierarchical structure for seamless integration

## Integration Components

### 1. The Bridge: `decon_trainer.py`

Located in `dr_exp/trainers/decon_trainer.py`, this module bridges the two systems:

```python
def train_classification(
    config: DictConfig,
    job_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    storage_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Main entry point for dr_exp to train deconCNN models."""
    
    # Initialize structured logger for dr_exp
    if storage_path:
        logger = StructuredLogger(
            log_dir=storage_path,
            job_id=job_id,
            worker_id=worker_id
        )
    
    # Import deconCNN components
    from decon_cnn.factory import create_model, create_optimizer, create_lr_scheduler
    from decon_cnn.data import create_data_module
    from decon_cnn.callbacks import DrExpMetricsCallback
    
    # Create components
    data_module = create_data_module(config)
    model = create_model(config)
    
    # Setup callbacks including dr_exp integration
    callbacks = [
        DrExpMetricsCallback(logger=logger) if logger else None,
        # ... other callbacks
    ]
    
    # Train with PyTorch Lightning
    trainer = pl.Trainer(**config.trainer, callbacks=callbacks)
    trainer.fit(model, data_module)
    
    # Return results for dr_exp
    return {
        "final_metrics": trainer.callback_metrics,
        "best_model_path": checkpoint_callback.best_model_path,
        "artifacts": list(storage_path.glob("*")) if storage_path else []
    }
```

### 2. Metrics Integration: `DrExpMetricsCallback`

The callback in deconCNN captures PyTorch Lightning metrics:

```python
class DrExpMetricsCallback(Callback):
    """Bridges PyTorch Lightning metrics to dr_exp's StructuredLogger."""
    
    def __init__(self, logger: StructuredLoggerProtocol):
        self.logger = logger
    
    def on_train_epoch_end(self, trainer, pl_module):
        metrics = trainer.callback_metrics
        self.logger.log_metrics({
            "epoch": trainer.current_epoch,
            "phase": "train",
            **{k: v.item() for k, v in metrics.items() if "train" in k}
        })
    
    def on_validation_epoch_end(self, trainer, pl_module):
        metrics = trainer.callback_metrics
        self.logger.log_metrics({
            "epoch": trainer.current_epoch,
            "phase": "val",
            **{k: v.item() for k, v in metrics.items() if "val" in k}
        })
```

### 3. Protocol-Based Design

deconCNN defines a protocol that dr_exp implements:

```python
class StructuredLoggerProtocol(Protocol):
    """Protocol for structured logging systems."""
    
    def log_event(self, event_type: str, data: Dict[str, Any]) -> None: ...
    def log_metrics(self, metrics: Dict[str, Any]) -> None: ...
    def log_error(self, error: Exception, context: Dict[str, Any]) -> None: ...
```

## Job Execution Flow

### 1. Job Submission
```bash
dr_exp --base-path ./exp --experiment cifar10 job submit \
  --config-path exp_configs \
  --config-name step00_baseline \
  --priority 100 \
  --tags "baseline,resnet18"
```

### 2. Worker Claims Job
```python
# Worker process
job = job_db.claim_job(worker_id="worker-01")
config = OmegaConf.load(job.config_path)

# Hydra instantiation with runtime params
with hydra.initialize_config_dir(config_dir=str(config_dir)):
    cfg = hydra.compose(config_name=config_name)
    
    # Inject runtime parameters
    with open_dict(cfg):
        cfg.job_id = job.id
        cfg.worker_id = worker_id
        cfg.storage_path = storage_path
    
    # Execute the target function
    result = hydra.utils.call(cfg)
```

### 3. Storage Structure
```
storage/run_12345678-1234-1234-1234-123456789012/
├── config.json          # Complete hydra config
├── metrics.jsonl        # Structured metrics log
├── events.jsonl         # Training events log
├── checkpoints/         # Model checkpoints
│   ├── best.ckpt
│   └── last.ckpt
├── logs/               # Text logs
│   └── train.log
└── artifacts/          # Additional outputs
```

## Practical Examples

### 1. Parameter Sweep
```bash
# Submit sweep over learning rates and models
dr_exp --base-path ./exp --experiment cifar10 job sweep \
  --config exp_configs/step00_baseline.yaml \
  --params "model=resnet18_cifar,resnet50_cifar optimizer.lr=0.1,0.01,0.001" \
  --tags "lr_sweep"
```

### 2. Running with SLURM
```bash
# Submit SLURM job that spawns workers
sbatch scripts/slurm_launcher.sh \
  --experiment cifar10 \
  --workers-per-gpu 2 \
  --max-hours 47
```

### 3. Custom Training Function
```python
# Create your own training function
def train_custom_model(
    config: DictConfig,
    job_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    storage_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Custom training function compatible with dr_exp."""
    
    # Your training logic here
    # Must return dict with results
    return {
        "final_metrics": {...},
        "artifacts": [...]
    }
```

## Configuration Overrides

### 1. Command Line Overrides
```bash
dr_exp job submit \
  --config-path exp_configs \
  --config-name step00_baseline \
  --overrides "data.batch_size=256 trainer.max_epochs=200"
```

### 2. Config Composition
```yaml
# exp_configs/experiment.yaml
defaults:
  - config  # Base from deconCNN
  - override /model: resnet50_cifar
  - override /optimizer: adam
  - override /transforms: cifar10_augmented
  - _self_

# Override specific values
optimizer:
  lr: 0.001  # Override adam's default lr
  
trainer:
  max_epochs: 150  # Override base config
```

## Troubleshooting

### Common Issues

1. **Missing _target_ in config**
   - Error: `HydraException: Config has no '_target_' key`
   - Solution: Ensure job configs include `_target_` field

2. **Import errors in worker**
   - Error: `ModuleNotFoundError: No module named 'decon_cnn'`
   - Solution: Ensure deconCNN is in PYTHONPATH or installed

3. **Config composition failures**
   - Check that all referenced configs exist in the search path
   - Use `--config-path` to specify custom config directories

4. **Storage permission errors**
   - Ensure experiment directory has write permissions
   - Check that storage path is correctly passed to training function

### Debug Commands

```bash
# Validate experiment structure
dr_exp --base-path ./exp --experiment cifar10 validate

# Check job status
dr_exp --base-path ./exp --experiment cifar10 job list --verbose

# View job config
cat exp/cifar10/jobs/<job_id>.json | jq .config

# Check worker logs
tail -f exp/cifar10/logs/worker-01.log

# Manually run a job for debugging
dr_exp --base-path ./exp --experiment cifar10 job run-one <job_id>
```

## Best Practices

1. **Config Organization**
   - Keep model/optimizer/scheduler configs modular
   - Use meaningful defaults lists for composition
   - Document config parameters

2. **Error Handling**
   - Wrap training code in try/except blocks
   - Log errors with context using StructuredLogger
   - Return partial results on failure

3. **Resource Management**
   - Set appropriate GPU memory limits
   - Use gradient accumulation for large batches
   - Enable mixed precision training

4. **Monitoring**
   - Use structured logging for all metrics
   - Save intermediate checkpoints
   - Track system metrics (GPU utilization, memory)

## Advanced Topics

### Custom Callbacks
```python
class CustomDrExpCallback(Callback):
    def __init__(self, logger: StructuredLoggerProtocol):
        self.logger = logger
    
    def on_train_batch_end(self, trainer, pl_module, outputs, batch, batch_idx):
        if batch_idx % 100 == 0:
            self.logger.log_event("batch_milestone", {
                "batch": batch_idx,
                "loss": outputs["loss"].item()
            })
```

### Multi-Stage Training
```yaml
# Config with multiple stages
defaults:
  - config
  - _self_

_target_: "dr_exp.trainers.multi_stage_trainer.train"

stages:
  - name: "warmup"
    max_epochs: 10
    optimizer:
      lr: 0.01
  - name: "main"
    max_epochs: 90
    optimizer:
      lr: 0.1
```

### Remote Monitoring
```python
# Access experiment results via API
import requests

# Get experiment status
response = requests.get("http://api.example.com/experiments/cifar10/status")

# Query specific metrics
response = requests.post("http://api.example.com/query", json={
    "experiment": "cifar10",
    "metrics": ["val_acc", "train_loss"],
    "group_by": "epoch"
})
```