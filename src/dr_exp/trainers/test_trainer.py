"""Simple test trainer for worker testing."""

import time
import random
from pathlib import Path
from typing import Any

from dr_exp.logging.structured_logger import StructuredLogger


def train(
    job_id: str,
    worker_id: str,
    storage_path: str,
    epochs: int = 10,
    fail_rate: float = 0.0,
    **kwargs: Any,  # noqa: ANN401
) -> dict[str, Any]:
    """Simple test training function.

    Args:
        job_id: Job ID (injected by worker)
        worker_id: Worker ID (injected by worker)
        storage_path: Path to store artifacts (injected by worker)
        epochs: Number of epochs to simulate
        fail_rate: Probability of failure (for testing)
        **kwargs: Additional config parameters

    Returns:
        Dict with training results
    """
    # Initialize structured logger
    logger = StructuredLogger(storage_path, job_id, worker_id)

    # Log configuration
    config = {"epochs": epochs, "fail_rate": fail_rate, **kwargs}
    logger.log_config(config)

    print(f"Test trainer started: job_id={job_id}, epochs={epochs}")

    # Simulate failure if requested
    if fail_rate > 0 and random.random() < fail_rate:  # noqa: S311
        logger.log_event("training_failed", {"reason": "simulated_failure"})
        raise RuntimeError("Simulated training failure")

    # Create storage directory
    storage = Path(storage_path)
    storage.mkdir(parents=True, exist_ok=True)

    # Start training
    logger.log_event("training_start")

    # Simulate training with metrics
    for epoch in range(epochs):
        loss = 1.0 / (epoch + 1) + random.random() * 0.1  # noqa: S311
        accuracy = min(0.99, epoch / epochs + random.random() * 0.1)  # noqa: S311

        # Log metrics using structured logger
        metrics = {"epoch": epoch, "loss": loss, "accuracy": accuracy}
        logger.log_metrics(metrics, step=epoch)

        # Simulate computation time
        time.sleep(0.01)

    # Save final model (dummy file)
    model_file = storage / "model_final.pt"
    model_file.write_text(f"Dummy model for job {job_id}")
    logger.log_artifact(model_file, "model", {"job_id": job_id})

    logger.log_event("training_complete")

    # Get summary from logger
    summary = logger.get_summary()
    final_metrics = summary["final_metrics"]

    print(
        f"Test trainer completed: final_accuracy={final_metrics.get('accuracy', 0):.3f}"
    )

    return {
        "metrics": {
            "final_loss": final_metrics.get("loss"),
            "final_accuracy": final_metrics.get("accuracy"),
            "total_epochs": epochs,
        },
        "artifacts": {
            "metrics_file": str(logger.metrics_file),
            "model_file": str(model_file),
        },
    }
