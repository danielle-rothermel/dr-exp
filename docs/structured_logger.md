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

**Required Properties:**
- `run_id` – unique identifier for the logging session
- `paths` – path manager providing access to all file locations

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
The logger is configured with a simple base directory path:
```python
from dr_exp.logging import StructuredLogger

# Simple usage - creates standard directory structure
logger = StructuredLogger("/path/to/logs")

# Advanced usage - custom file organization
from dr_exp.logging.logger_paths import LoggerPathConfig
config = LoggerPathConfig(
    base_dir="/custom/logs",
    metrics_filename="training.jsonl",
    checkpoint_dir="models"
)
logger = StructuredLogger(config)
```

**Directory Structure:**
The logger automatically creates this structure:
```
log_dir/
├── metrics.jsonl       # Training metrics in JSON Lines format
├── checkpoints/        # Model checkpoints
├── artifacts/          # Registered artifacts
└── errors.log          # Error log (non-debug mode)
```

## Usage Patterns

### In Training Code

```python
from dr_exp.logging.base_logger import BaseLogger

def train(logger: BaseLogger) -> Dict[str, Any]:
    for epoch in range(num_epochs):
        # Training logic...
        logger.log({"epoch": epoch, "train_loss": loss, "val_acc": acc})
        
        if should_checkpoint:
            logger.save_checkpoint(model.state_dict(), f"epoch_{epoch}")
    
    # Create and register artifacts in logger's artifact directory
    plot_path = logger.paths.artifact_path("model_plot.png")
    create_model_plot(plot_path)
    logger.log_artifact(plot_path)
    
    # Finalize and get summary
    summary = logger.finalize()
    return {"status": "success", **summary}
```

### In Worker Logic

```python
from dr_exp.logging.structured_logger import StructuredLogger

def run_worker(work_dir: str, trainer_fn, logger_cls: type[BaseLogger] = StructuredLogger):
    # Create logger with work directory
    logger = logger_cls(work_dir)
    
    # Train and get results
    result = trainer_fn(logger)
    metadata = logger.finalize()
    
    # Upload artifacts using logger's file paths
    upload_file(logger.paths.metrics_path, "metrics.jsonl")
    upload_directory(logger.paths.checkpoint_dir, "checkpoints/")
    upload_directory(logger.paths.artifact_dir, "artifacts/")
```

## Extending the System

To create custom logger implementations (e.g., for cloud logging):

1. Inherit from `BaseLogger`
2. Implement all abstract methods and the `paths` property
3. Ensure thread-safety if needed
4. Follow the same return value patterns for `finalize()`
5. Consider using `LoggerPathManager` for consistent path handling

This design allows the experiment manager to support different logging backends while maintaining a consistent interface for training code.
