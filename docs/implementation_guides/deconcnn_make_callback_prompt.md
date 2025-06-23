# DeconCNN MetricsCallback Implementation

## Goal
Create a PyTorch Lightning callback that bridges deconCNN's training system with dr_exp's StructuredLogger, enabling metrics tracking and artifact management.

## Context
- deconCNN uses PyTorch Lightning for training
- dr_exp expects trainers to use StructuredLogger for metrics/artifacts
- The integration must capture all training events and metrics
- Following fail-fast philosophy: simple, direct implementation

## Implementation Tasks

### 1. Fix Import Path
In `scripts/run_decon_worker.py`, line 19:
```python
# WRONG:
config["_target_"] = "dr_exp.training.decon_trainer.train_classification"

# CORRECT:
config["_target_"] = "dr_exp.trainers.decon_trainer.train_classification"
```

### 2. Create MetricsCallback for deconCNN
Create a new file in the deconCNN library (wherever callbacks are stored) with this callback:

```python
"""dr_exp integration callback for deconCNN."""
import pytorch_lightning as pl
from pathlib import Path
from typing import Any, Dict, Optional


class DrExpMetricsCallback(pl.Callback):
    """Callback that logs metrics to dr_exp's StructuredLogger."""
    
    def __init__(self, logger):
        """Initialize callback with StructuredLogger instance.
        
        Args:
            logger: StructuredLogger instance from dr_exp
        """
        super().__init__()
        self.logger = logger
        self.current_epoch = 0
        
    def on_train_start(self, trainer: pl.Trainer, pl_module: pl.LightningModule) -> None:
        """Log training start event."""
        self.logger.log_event("training_start", {
            "max_epochs": trainer.max_epochs,
            "devices": trainer.num_devices,
        })
    
    def on_train_epoch_start(self, trainer: pl.Trainer, pl_module: pl.LightningModule) -> None:
        """Track current epoch."""
        self.current_epoch = trainer.current_epoch
        
    def on_train_epoch_end(self, trainer: pl.Trainer, pl_module: pl.LightningModule) -> None:
        """Log epoch metrics."""
        # Collect all metrics
        metrics = {}
        
        # Get metrics from trainer
        for key, value in trainer.callback_metrics.items():
            if hasattr(value, 'item'):
                metrics[key] = value.item()
            else:
                metrics[key] = value
                
        # Add epoch number
        metrics['epoch'] = self.current_epoch
        
        # Log to StructuredLogger
        self.logger.log_metrics(metrics, step=self.current_epoch)
    
    def on_validation_epoch_end(self, trainer: pl.Trainer, pl_module: pl.LightningModule) -> None:
        """Log validation metrics."""
        # Validation metrics are already included in callback_metrics
        # They'll be logged in on_train_epoch_end
        pass
        
    def on_save_checkpoint(self, trainer: pl.Trainer, pl_module: pl.LightningModule, checkpoint: Dict[str, Any]) -> None:
        """Log checkpoint save event."""
        epoch = checkpoint.get('epoch', self.current_epoch)
        ckpt_path = trainer.checkpoint_callback.best_model_path
        
        if ckpt_path:
            self.logger.log_artifact(
                Path(ckpt_path), 
                "checkpoint",
                {"epoch": epoch, "score": trainer.checkpoint_callback.best_model_score}
            )
    
    def on_train_end(self, trainer: pl.Trainer, pl_module: pl.LightningModule) -> None:
        """Log training completion."""
        self.logger.log_event("training_complete", {
            "epochs_completed": trainer.current_epoch + 1,
        })
        
    def on_exception(self, trainer: pl.Trainer, pl_module: pl.LightningModule, exception: BaseException) -> None:
        """Log training failure."""
        self.logger.log_event("training_failed", {
            "error": str(exception),
            "epoch": self.current_epoch,
        })
```

### 3. Update decon_trainer.py
Replace the mock implementation in `src/dr_exp/trainers/decon_trainer.py` with:

```python
"""DeconCNN integration for dr_exp."""
from pathlib import Path
from typing import Dict, Any, Optional
import traceback
import pytorch_lightning as pl

from ..logging.structured_logger import StructuredLogger

# Import from deconCNN
from deconCNN import factory
from deconCNN.callbacks import DrExpMetricsCallback  # The callback we created above


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

## Key Implementation Points

1. **DrExpMetricsCallback**: 
   - Captures ALL PyTorch Lightning training events
   - Logs metrics after each epoch (train + validation together)
   - Records checkpoint saves with metadata
   - Handles exceptions properly

2. **decon_trainer.py Integration**:
   - Uses deconCNN's factory pattern to create components
   - Injects our callback into the trainer configuration
   - Sets storage_path as default_root_dir for checkpoints
   - Returns metrics and artifacts in dr_exp's expected format

3. **Error Handling**:
   - Logs failures to both StructuredLogger and error.txt
   - Preserves full traceback for debugging
   - Follows fail-fast philosophy (no recovery attempts)

## Testing the Integration

After implementation, test with:
```bash
# Fix the import first
sed -i '' 's/dr_exp.training.decon_trainer/dr_exp.trainers.decon_trainer/g' scripts/run_decon_worker.py

# Run a test job
uvrp scripts/run_decon_worker.py --mode files_local --base-path ./test_decon

# Check results
ls -la ./test_decon/job_data/
cat ./test_decon/job_data/*/metrics.jsonl
```

## Notes
- The callback must be added to deconCNN's codebase since it needs to import from there
- The integration is minimal - just a callback and updated trainer function
- All existing deconCNN configs work unchanged
- StructuredLogger handles all artifact tracking