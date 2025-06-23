# Complete deconCNN Integration

## Goal
Fix the deconCNN integration by updating import paths and replacing mock implementation with real deconCNN usage.

## Context
- DrExpMetricsCallback already exists in deconCNN repository
- Current decon_trainer.py has mock implementation
- Import path in run_decon_worker.py is incorrect
- Following fail-fast philosophy: simple, direct fixes only

## Implementation Tasks

### Task 1: Fix Import Path in run_decon_worker.py
Change line 11 from:
```python
from dr_exp.training.decon_trainer import train as decon_train
```

To:
```python
from dr_exp.trainers.decon_trainer import train_classification as decon_train
```

### Task 2: Update decon_trainer.py with Real Implementation
Replace the ENTIRE contents of `src/dr_exp/trainers/decon_trainer.py` with:

```python
"""DeconCNN integration for dr_exp."""
from pathlib import Path
from typing import Dict, Any, Optional
import traceback
import pytorch_lightning as pl

from ..logging.structured_logger import StructuredLogger

# Import from deconCNN
from deconcnn import factory
from deconcnn.callbacks import DrExpMetricsCallback


def train_classification(
    job_id: str,
    worker_id: str, 
    storage_path: str,
    **config: Any,
) -> Dict[str, Any]:
    """Train a classification model using deconCNN.
    
    Args:
        job_id: Job ID (injected by worker)
        worker_id: Worker ID (injected by worker)
        storage_path: Path to store artifacts (injected by worker)
        **config: All config parameters for deconCNN
        
    Returns:
        Dictionary with training results
    """
    # Initialize logger
    logger = StructuredLogger(storage_path, job_id, worker_id)
    
    # Log full configuration
    logger.log_config(config)
    
    try:
        # Create deconCNN components using factory
        model = factory.create_model(config)
        data_module = factory.create_data_module(config)
        
        # Create our metrics callback
        metrics_callback = DrExpMetricsCallback(logger)
        
        # Get trainer config and add our callback
        trainer_config = config.get('trainer', {})
        existing_callbacks = trainer_config.get('callbacks', [])
        trainer_config['callbacks'] = existing_callbacks + [metrics_callback]
        
        # Set default_root_dir to storage_path
        trainer_config['default_root_dir'] = storage_path
        
        # Create trainer with updated config
        config['trainer'] = trainer_config
        trainer = factory.create_trainer(config)
        
        # Train the model
        trainer.fit(model, data_module)
        
        # Get final metrics from logger summary
        summary = logger.get_summary()
        final_metrics = summary.get("final_metrics", {})
        
        # Find best checkpoint path
        best_ckpt_path = None
        if hasattr(trainer.checkpoint_callback, 'best_model_path'):
            best_ckpt_path = trainer.checkpoint_callback.best_model_path
            
        # Build artifacts dict
        artifacts = {
            "metrics_path": str(logger.metrics_file),
            "config_path": str(logger.config_file),
            "events_path": str(logger.events_file),
        }
        
        if best_ckpt_path:
            artifacts["best_checkpoint"] = str(best_ckpt_path)
            
        # Add any model files in storage_path
        for p in Path(storage_path).glob("*.ckpt"):
            artifacts[f"checkpoint_{p.stem}"] = str(p)
            
        return {
            "metrics": final_metrics,
            "artifacts": artifacts,
        }
        
    except Exception as e:
        # Log the error
        logger.log_event("training_failed", {
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        
        # Save error details
        error_file = Path(storage_path) / "error.txt"
        error_file.write_text(f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")
        
        raise
```

### Task 3: Add deconCNN Dependency
Run this command to add deconCNN as a dependency:
```bash
uv add deconcnn --source path --path /Users/daniellerothermel/drotherm/repos/deconCNN
```

### Task 4: Create Test Configuration
Create `configs/test_decon_integration.yaml`:
```yaml
_target_: dr_exp.trainers.decon_trainer.train_classification

# Model configuration
model:
  _target_: deconcnn.models.classification.SimpleClassifier
  num_classes: 10
  hidden_dim: 128

# Data configuration  
data:
  _target_: deconcnn.data.dummy.DummyDataModule
  batch_size: 32
  num_samples: 1000

# Trainer configuration
trainer:
  max_epochs: 3
  accelerator: cpu
  devices: 1
  enable_checkpointing: true
  enable_progress_bar: false
  logger: false  # We use our own logger

# Optimizer configuration
optim:
  _target_: torch.optim.Adam
  lr: 0.001
```

## Validation Steps

### Step 1: Verify Import Fix
```bash
# Check the import is correct
grep -n "from dr_exp" scripts/run_decon_worker.py

# Expected output:
# 8:from dr_exp.utils.factory import create_system, SystemConfig
# 9:from dr_exp.job_db import JobDBConfig
# 10:from dr_exp.manage.worker import run_worker
# 11:from dr_exp.trainers.decon_trainer import train_classification as decon_train
# 12:from dr_exp.logging.structured_logger import StructuredLogger
```

### Step 2: Run Code Quality Checks
```bash
# Must pass without errors
ckdr

# Expected output:
# All checks passed!
```

### Step 3: Test Basic Integration
```bash
# Create test directory
mkdir -p /tmp/decon_test

# Submit a test job
uvrp scripts/upload_configs.py \
  --base-path /tmp/decon_test \
  --mode files_local \
  --base-config-path configs \
  --config-name test_decon_integration \
  --priority 100

# Run the decon worker
uvrp scripts/run_decon_worker.py \
  --base-path /tmp/decon_test \
  --mode files_local \
  --worker-id test_decon \
  --work-dir /tmp/decon_work

# Check job completed
ls -la /tmp/decon_test/job_data/
cat /tmp/decon_test/job_data/*/status

# Expected: status = "completed"
```

### Step 4: Verify Artifacts Created
```bash
# List storage directory
ls -la /tmp/decon_test/storage/*/

# Expected files:
# - config.json
# - events.jsonl
# - metadata.json
# - metrics.jsonl
# - *.ckpt (checkpoint files)

# Check metrics were logged
cat /tmp/decon_test/storage/*/metrics.jsonl | head -3

# Expected: JSON lines with epoch metrics
```

### Step 5: Run Integration Test
Create `test_decon_integration.py`:
```python
import tempfile
import json
from pathlib import Path

from dr_exp.core.job_db import JobDB
from dr_exp.worker.base import Worker


def test_decon_real_integration():
    """Test real deconCNN integration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test", validate=False)
        
        # Create job with deconCNN config
        config = {
            "_target_": "dr_exp.trainers.decon_trainer.train_classification",
            "model": {
                "_target_": "deconcnn.models.classification.SimpleClassifier",
                "num_classes": 5,
                "hidden_dim": 64
            },
            "data": {
                "_target_": "deconcnn.data.dummy.DummyDataModule",
                "batch_size": 16,
                "num_samples": 100
            },
            "trainer": {
                "max_epochs": 2,
                "accelerator": "cpu"
            }
        }
        
        job_id = job_db.create_job(config)
        
        # Run worker
        worker = Worker(job_db=job_db, worker_id="test")
        status = worker.run_one_job()
        
        assert status == "completed"
        
        # Check artifacts
        storage_path = job_db.get_storage_path(job_id)
        assert (storage_path / "metrics.jsonl").exists()
        assert (storage_path / "config.json").exists()
        
        # Verify metrics logged
        with open(storage_path / "metrics.jsonl") as f:
            lines = f.readlines()
            assert len(lines) >= 2  # At least 2 epochs
            
            # Check first epoch has expected keys
            first = json.loads(lines[0])
            assert "metrics" in first
            assert "epoch" in first["metrics"]


if __name__ == "__main__":
    test_decon_real_integration()
    print("✓ Integration test passed!")
```

Run test:
```bash
uvrp test_decon_integration.py
```

## Common Mistakes to AVOID

**DO NOT:**
- Import from `dr_exp.training` - that directory only has `__init__.py`
- Try to make the integration "smart" - keep it simple
- Add error recovery - follow fail-fast philosophy
- Forget to add deconCNN dependency
- Skip running `ckdr` after changes

**DO NOT attempt these incorrect fixes:**
```python
# WRONG - trying to be clever with imports
try:
    from deconcnn import factory
except ImportError:
    factory = None  # NO! Fail fast

# WRONG - adding recovery logic
if not trainer.checkpoint_callback:
    trainer.checkpoint_callback = ModelCheckpoint()  # NO! Let it fail

# WRONG - hidden behavior
if "trainer" not in config:
    config["trainer"] = {}  # NO! Be explicit
```

## Expected Results

After implementation:
1. `run_decon_worker.py` imports from correct path
2. Real deconCNN trains models (not mock)
3. DrExpMetricsCallback logs all metrics to StructuredLogger
4. All artifacts saved to storage_path
5. Worker completes jobs successfully

## Troubleshooting

If you see "ModuleNotFoundError: No module named 'deconcnn'":
- Ensure you ran the `uv add` command
- Check deconCNN path exists: `/Users/daniellerothermel/drotherm/repos/deconCNN`

If you see "AttributeError: module 'deconcnn' has no attribute 'factory'":
- deconCNN may not have factory pattern yet
- Check what's available: `uvrp -c "import deconcnn; print(dir(deconcnn))"`

If worker fails with "no_job":
- Check job was created: `ls -la /tmp/decon_test/job_data/`
- Ensure using same --base-path and --mode for all commands