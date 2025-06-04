# Training Examples (`docs/train_examples.md`)

The `src/dr_exp/train_examples` package contains a minimal training loop and a set of Hydra configuration files used for tests and demonstrations.

## Files

- `dummy_trainer.py` – simple `train()` function that logs metrics, checkpoints and a dummy artifact using `StructuredLogger`.
- `configs/` – Hydra config tree with a base `config.yaml` and subdirectories for model and optimizer options.

## Usage

These examples are not intended for serious training but show how a user training script can interact with the Experiment Manager.  The configs can be uploaded using `scripts/upload_configs.py` or the `manager_cli upload-configs` command.

`dummy_trainer.train()` accepts a configuration object and an optional `StructuredLogger` instance.  It simulates a few epochs of training, emits checkpoint files and returns summary statistics that are stored with each job.
