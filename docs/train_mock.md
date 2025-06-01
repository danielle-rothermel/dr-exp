# Mock Training Module Specification (`docs/train_mock.md`)

## Purpose

This module provides a lightweight, deterministic implementation of the `train(cfg, logger)` interface that simulates a training run. It is used to test the Experiment Manager infrastructure without needing real training logic, GPU hardware, or heavy libraries like PyTorch.

The mock trainer enables validation of:

* Hydra configuration injection and job claiming
* Logging behavior with `StructuredLogger`
* Worker lifecycle and failure handling
* Upload and cleanup logic

---

## Interface Definition

```python
def train(cfg: DictConfig, logger: Optional[StructuredLogger] = None) -> dict:
    ...
```

This should match the interface contract used by real training scripts, with behavior that:

* Runs for a short time (e.g., simulates `cfg.train.num_epochs` iterations)
* Logs structured scalar metrics to the logger
* Saves one or more fake checkpoints
* Registers artifacts (e.g., static plots, logs, etc.)
* Returns metadata as expected by the experiment manager

---

## Simulated Behavior

* **Epoch loop**: simulate N steps (e.g., epochs), using `time.sleep()`

  * No failure injection is included by default. This can be added later if deeper infrastructure testing is needed.
* **Metric generation**: produce static, deterministic values for `train_loss`, `val_loss`, `train_acc`, `val_acc` as functions of epoch

  * No support for parametric variation of curve shape; static output is sufficient for verifying infrastructure behavior.
* **Checkpointing**: save 1–2 dummy checkpoint files using `logger.save_checkpoint()`
* **Artifacts**: copy a sample image or generate a dummy plot and register it with `logger.log_artifact()`
* **Final result**: return all required metadata fields

---

## Return Value

The dictionary returned by `train()` must include:

```python
{
  "final_val_acc": 0.92,
  "final_train_loss": 0.24,
  "num_epochs": 10,
  "status": "success",
  "metrics_path": "/path/to/metrics.jsonl",
  "artifacts_path": "/path/to/artifacts/",
  "num_checkpoints": 2
}
```

All paths must come from `cfg.logging`, not hardcoded.

---

## Logging and Paths

This mock trainer will live in the `tests/` section of the codebase and is intended for validation purposes only—not part of runtime logic.
The logger must be used as follows:

```python
logger.log({"epoch": epoch, "train_loss": 0.5, "val_acc": 0.8})
logger.save_checkpoint({...}, tag=f"epoch_{epoch}")
logger.log_artifact("loss_plot.png")
```

All paths must use the `cfg.logging` keys injected by the experiment manager:

* `cfg.logging.out_path`
* `cfg.logging.checkpoint_dir`
* `cfg.logging.artifact_dir`

---

## Testing Requirements

Tests for this mock trainer should validate:

* `train()` completes without error
* Expected number of metrics are logged
* `.jsonl` file is created and well-formed
* Artifacts and checkpoints exist and match expected structure
* Returned dictionary has correct keys and types

➡️ See: `tests/test_train_mock.py`

---

