# Structured Logging System

The structured logging system provides a standardized interface for capturing metrics, checkpoints, and artifacts during training runs. The system is built around an abstract base class that defines the core logging interface.

## Architecture

### Base Interface

`dr_exp.logging.base_logger.BaseLogger` defines the abstract interface that all logger implementations must follow:

**Required Methods:**
- `log(metrics)` – log metrics data to storage
- `save_checkpoint(state_dict, tag)` – save model checkpoints
- `log_artifact(path)` – register artifacts for tracking/upload
- `finalize()` – close resources and return summary metadata

**Required Attributes:**
- `run_id` – unique identifier for the logging session

### Implementations

#### StructuredLogger

`dr_exp.logging.structured_logger.StructuredLogger` is the default filesystem-based implementation:

**Key Features:**
- Appends metrics to a JSON Lines file with file locking for concurrency
- Saves checkpoints optionally compressed with gzip
- Records artifact file paths for later upload
- Produces comprehensive summary metadata when finalized
- Error handling with optional debug mode for development

**Configuration:**
The logger is configured via a `logging` section in the experiment config:
```yaml
logging:
  out_path: path/to/metrics.jsonl
  artifact_dir: path/to/artifacts/
  checkpoint_dir: path/to/checkpoints/
```

## Usage Patterns

### In Training Code

```python
from dr_exp.logging.base_logger import BaseLogger

def train(cfg: Any, logger: BaseLogger) -> Dict[str, Any]:
    for epoch in range(num_epochs):
        # Training logic...
        logger.log({"epoch": epoch, "train_loss": loss, "val_acc": acc})
        
        if should_checkpoint:
            logger.save_checkpoint(model.state_dict(), f"epoch_{epoch}")
    
    # Register artifacts
    logger.log_artifact("model_plot.png")
    
    # Finalize and get summary
    summary = logger.finalize()
    return {"status": "success", **summary}
```

### In Worker Logic

```python
from dr_exp.logging.structured_logger import StructuredLogger

def run_worker(trainer_fn, logger_cls: type[BaseLogger] = StructuredLogger):
    logger = logger_cls(cfg)
    result = trainer_fn(cfg, logger)
    metadata = logger.finalize()
    # Upload artifacts using metadata paths
```

## Extending the System

To create custom logger implementations (e.g., for cloud logging):

1. Inherit from `BaseLogger`
2. Implement all abstract methods
3. Ensure thread-safety if needed
4. Follow the same return value patterns for `finalize()`

This design allows the experiment manager to support different logging backends while maintaining a consistent interface for training code.
