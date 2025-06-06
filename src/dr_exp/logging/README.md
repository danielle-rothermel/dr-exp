# Structured Logging Utilities

This package provides structured logging implementations for capturing metrics, checkpoints, and artifacts during training runs. All implementations follow a common interface defined by an abstract base class.

## Modules

- `base_logger.py` – abstract base class defining the logging interface that all implementations must follow.
- `structured_logger.py` – filesystem-based implementation using local files for metrics storage, checkpoint saving, and artifact tracking.
- `logger_paths.py` – path management utilities for organizing logger output files.
- `__init__.py` exports :class:`~dr_exp.logging.BaseLogger` and :class:`~dr_exp.logging.StructuredLogger`.

## Interface

All logger implementations provide the following core functionality:

**Required Methods:**
- `log()` – log metrics data to storage
- `save_checkpoint()` – save model checkpoints with optional compression
- `log_artifact()` – register artifacts for tracking and upload
- `finalize()` – close resources and return summary metadata

**Required Properties:**
- `run_id` – unique identifier for the logging session
- `paths` – path manager providing access to all file locations

## Usage

### Basic Usage

```python
from dr_exp.logging import StructuredLogger

# Create logger with a base directory
logger = StructuredLogger("/path/to/logs")

# The logger automatically creates the following structure:
# /path/to/logs/
# ├── metrics.jsonl
# ├── checkpoints/
# ├── artifacts/
# └── errors.log

# Log metrics
logger.log({"epoch": 1, "train_loss": 0.5, "val_acc": 0.8})

# Save checkpoint
logger.save_checkpoint(model.state_dict(), "epoch_1")

# Register artifacts
logger.log_artifact("loss_plot.png")

# Access file paths
print(f"Metrics saved to: {logger.paths.metrics_path}")
print(f"Checkpoints in: {logger.paths.checkpoint_dir}")
print(f"Artifacts in: {logger.paths.artifact_dir}")

# Finalize and get summary
summary = logger.finalize()
print(f"Logged {summary['num_metrics']} metrics")
```

### Type-Safe Interface

```python
from dr_exp.logging.base_logger import BaseLogger
from dr_exp.logging.structured_logger import StructuredLogger

def train_model(logger: BaseLogger) -> Dict[str, Any]:
    # Training code that works with any logger implementation
    logger.log({"step": 1, "loss": 0.1})
    return {"status": "success"}

# Use with any logger implementation
logger = StructuredLogger("/path/to/logs")
result = train_model(logger)
```

## Features

### Thread Safety
The `StructuredLogger` implementation uses file locking to ensure thread-safe operation when multiple processes write to the same metrics file.

### Error Handling
Loggers support both production and debug modes:
- **Production mode**: Errors are logged to a separate error file
- **Debug mode**: Errors are raised immediately for development

### Checkpoint Compression
Checkpoints can be optionally compressed using gzip to save disk space:

```python
logger = StructuredLogger("/path/to/logs", compress_checkpoints=True)
```

### Artifact Tracking
The system tracks all artifacts registered during training and includes their paths in the finalization summary for upload to persistent storage.

## Advanced Configuration

For custom file organization, use `LoggerPathConfig`:

```python
from dr_exp.logging import StructuredLogger
from dr_exp.logging.logger_paths import LoggerPathConfig

config = LoggerPathConfig(
    base_dir="/custom/logs",
    metrics_filename="training_metrics.jsonl",
    checkpoint_dir="models",
    artifact_dir="outputs"
)
logger = StructuredLogger(config)
```

## Extending

To create custom logger implementations:

1. Inherit from `BaseLogger`
2. Implement all abstract methods and the `paths` property
3. Ensure proper error handling
4. Follow the established patterns for return values

This modular design allows the experiment management system to support different logging backends while maintaining a consistent interface for training code.