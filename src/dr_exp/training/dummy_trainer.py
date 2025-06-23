"""Dummy trainer for testing config sweeps."""

import time
import random
from pathlib import Path
from typing import Dict, Any

from ..logging.structured_logger import StructuredLogger


def train_dummy(
    job_id: str,
    worker_id: str,
    storage_path: str,
    epochs: int = 10,
    batch_size: int = 32,
    lr: float = 0.001,
    model: str = "resnet18",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Dummy training function for testing.

    Args:
        job_id: Job ID (injected by worker)
        worker_id: Worker ID (injected by worker)
        storage_path: Path to store artifacts (injected by worker)
        epochs: Number of epochs to simulate
        batch_size: Batch size
        lr: Learning rate
        model: Model name
        **kwargs: Additional config parameters

    Returns:
        Dict with training results
    """
    # Initialize structured logger
    logger = StructuredLogger(storage_path, job_id, worker_id)

    # Log configuration
    config = {
        "epochs": epochs,
        "batch_size": batch_size,
        "lr": lr,
        "model": model,
        **kwargs,
    }
    logger.log_config(config)

    print(f"Dummy trainer started: job_id={job_id}, model={model}, epochs={epochs}")

    # Create storage directory
    storage = Path(storage_path)
    storage.mkdir(parents=True, exist_ok=True)

    # Start training
    logger.log_event("training_start")

    # Simulate training with metrics
    for epoch in range(epochs):
        loss = 1.0 / (epoch + 1) + random.random() * 0.1
        accuracy = min(0.99, epoch / epochs + random.random() * 0.1)

        # Log metrics using structured logger
        metrics = {"epoch": epoch, "loss": loss, "accuracy": accuracy}
        logger.log_metrics(metrics, step=epoch)

        # Simulate computation time
        time.sleep(0.01)

    # Save final model (dummy file)
    model_file = storage / "model_final.pt"
    model_file.write_text(f"Dummy model {model} for job {job_id}")
    logger.log_artifact(model_file, "model", {"job_id": job_id, "model": model})

    logger.log_event("training_complete")

    # Get summary from logger
    summary = logger.get_summary()
    final_metrics = summary["final_metrics"]

    print(
        f"Dummy trainer completed: model={model}, final_accuracy={final_metrics.get('accuracy', 0):.3f}"
    )

    return {
        "metrics": {
            "final_loss": final_metrics.get("loss"),
            "final_accuracy": final_metrics.get("accuracy"),
            "total_epochs": epochs,
            "model": model,
        },
        "artifacts": {
            "metrics_file": str(logger.metrics_file),
            "model_file": str(model_file),
        },
    }
