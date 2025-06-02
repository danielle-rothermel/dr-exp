# StructuredLogger Specification (`docs/logger.md`)

## Purpose

The `StructuredLogger` is a multiprocessing-safe, modular logging utility used by training workers to:

* Write scalar metrics in structured `.jsonl` format
* Save model checkpoints to a defined directory
* Register additional artifacts (e.g., plots, configs, logs)
* Track artifact paths for post-run upload and indexing

The logger does **not** handle actual uploading to Supabase or blob storage — this responsibility is owned by the worker supervisor.

---

## Responsibilities

### ✅ Must:

* Log scalar values (e.g., loss, accuracy) to a structured log file
* Be safe for multiprocessing usage across workers on the same machine
* Save model checkpoints with filename tags (e.g., `epoch_10.pt`)
* Track all saved artifacts in an internal registry
* Provide a `.finalize()` method that flushes logs, closes files, and outputs metadata

### ❌ Must Not:

* Handle any HTTP or Supabase uploads
* Impose file format restrictions on user-saved artifacts
* Make assumptions about training framework (must remain agnostic)

---

## Interface Definition

```python
class StructuredLogger:
    def __init__(self, cfg: DictConfig, compress_checkpoints: bool = False, debug: bool = False): .....

    def log(self, metrics: dict): ...
    def save_checkpoint(self, state_dict: dict, tag: str): ...
    def log_artifact(self, path: str): ...
    def finalize(self) -> dict: ...
```

### `log(metrics: dict)`

Appends a JSON-serializable dictionary (e.g., `{"epoch": 10, "val_loss": 0.83}`) to `metrics.jsonl`.

* Injects timestamp and run ID internally
* Optional: buffer + flush to disk every N writes (configurable)

### `save_checkpoint(state_dict: dict, tag: str)`

Saves a checkpoint file to `cfg.logging.checkpoint_dir` with name `checkpoint_{tag}.pt.gz` if compression is enabled.

* Compression format is gzip, controlled by the `compress_checkpoints` argument at logger initialization
* Also logs metadata (e.g., bytes written, path) to internal registry

### `log_artifact(path: str)`

Registers an existing file or directory path to be tracked as an artifact

* No copying or moving occurs — the logger just records it for later upload
* Must work with both files (e.g., PNG, log) and folders (e.g., `artifacts/`)

### `finalize() -> dict`

Closes the log file, flushes all buffers, and returns summary metadata:

```python
{
  "metrics_path": "/output/metrics.jsonl",
  "num_metrics": 378,
  "artifact_paths": [...],
  "num_checkpoints": 3,
  "finalize_success": True,
}
```

This return value is passed to the worker for inclusion in the job completion metadata.

---

## Configuration Requirements

The logger is initialized with `cfg.logging`, which must include:

```yaml
cfg.logging:
  out_path: /path/to/metrics.jsonl
  artifact_dir: /path/to/artifacts/
  checkpoint_dir: /path/to/checkpoints/
  log_file: /path/to/training.log  # optional
```

These values are injected by the experiment worker (`dr_exp.worker.run_worker`).

---

## Error Handling and Concurrency

### Debug Mode

If `debug=True` (set at logger initialization), all write or save failures will raise exceptions.
If `debug=False`, failures are logged to a dedicated `logger_error.log` file and the logger attempts to continue safely.

* Multiple training processes may call `.log()` concurrently on the same machine
* Implementation must:

  * Use file-level locks or safe append mechanisms
  * Handle partial failures gracefully (e.g., fallback to in-memory queue)
* `.finalize()` must be idempotent and safe to call multiple times

---

## Test Coverage Requirements

Tests for the logger should verify:

* Valid JSON lines are written and flush correctly
* Checkpoints are saved with correct naming and content
* Artifact paths are tracked and accessible post-finalize
* Concurrency behavior under multiple processes writing concurrently

➡️ See: `tests/test_logger.py`

---

