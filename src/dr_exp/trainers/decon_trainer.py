"""DeconCNN integration for dr_exp."""

from pathlib import Path
from typing import Any
import traceback
from omegaconf import OmegaConf

from dr_exp.logging.structured_logger import StructuredLogger

# Import from deconCNN
from deconcnn import factory
from deconcnn.callbacks import DrExpMetricsCallback


def train_classification(
    job_id: str,
    worker_id: str,
    storage_path: str,
    **config: Any,  # noqa: ANN401
) -> dict[str, Any]:
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
        # Convert config to DictConfig for deconCNN
        cfg = OmegaConf.create(config)

        # Set default_root_dir to storage_path
        trainer_config = cfg.get("trainer", {})
        trainer_config["default_root_dir"] = storage_path
        cfg["trainer"] = trainer_config

        # Create all deconCNN components using factory
        model, data_module, trainer = factory.create_training_components(
            cfg,
            dataset_name=cfg.get("dataset", "cifar10"),
            num_classes=cfg.get("num_classes", 10),
        )

        # Add our metrics callback to the trainer
        metrics_callback = DrExpMetricsCallback(logger)
        trainer.callbacks.append(metrics_callback)  # type: ignore[attr-defined]

        # Train the model
        trainer.fit(model, data_module)

        # Get final metrics from logger summary
        summary = logger.get_summary()
        final_metrics = summary.get("final_metrics", {})

        # Find best checkpoint path
        best_ckpt_path = None
        if trainer.checkpoint_callback and hasattr(
            trainer.checkpoint_callback, "best_model_path"
        ):
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
        logger.log_event(
            "training_failed", {"error": str(e), "traceback": traceback.format_exc()}
        )

        # Save error details
        error_file = Path(storage_path) / "error.txt"
        error_file.write_text(f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")

        raise
