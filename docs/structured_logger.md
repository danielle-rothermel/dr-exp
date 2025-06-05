# Structured Logger (`docs/structured_logger.md`)

`dr_exp.logging.structured_logger.StructuredLogger` is a lightweight utility used by workers to capture metrics, checkpoints and arbitrary artifact files during training.

## Key Features

- Appends metrics to a JSON Lines file.
- Saves checkpoints optionally compressed with gzip.
- Records additional artifact file paths for later upload.
- Produces a summary dictionary when finalized containing paths and counts.

The logger is configured via a `logging` section in the experiment config specifying `out_path`, `artifact_dir` and `checkpoint_dir`.  Workers pass the resulting metadata back to the job database when a run finishes.
