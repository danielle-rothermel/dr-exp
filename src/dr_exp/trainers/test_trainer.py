"""Simple test trainer for worker testing."""

import time
import random
from pathlib import Path
from typing import Dict, Any


def train(
    job_id: str,
    worker_id: str,
    storage_path: str,
    epochs: int = 10,
    fail_rate: float = 0.0,
    **kwargs: Any,
) -> Dict[str, Any]:
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
    print(f"Test trainer started: job_id={job_id}, epochs={epochs}")

    # Simulate failure if requested
    if fail_rate > 0 and random.random() < fail_rate:
        raise RuntimeError("Simulated training failure")

    # Create storage directory
    storage = Path(storage_path)
    storage.mkdir(parents=True, exist_ok=True)

    # Simulate training with metrics
    metrics = []
    for epoch in range(epochs):
        loss = 1.0 / (epoch + 1) + random.random() * 0.1
        accuracy = min(0.99, epoch / epochs + random.random() * 0.1)

        metrics.append({"epoch": epoch, "loss": loss, "accuracy": accuracy})

        # Simulate computation time
        time.sleep(0.01)

        # Save metrics to file
        metrics_file = storage / "metrics.jsonl"
        with open(metrics_file, "a") as f:
            import json

            f.write(json.dumps(metrics[-1]) + "\n")

    # Save final model (dummy file)
    model_file = storage / "model_final.pt"
    model_file.write_text(f"Dummy model for job {job_id}")

    # Return final metrics
    final_metrics = {
        "final_loss": metrics[-1]["loss"],
        "final_accuracy": metrics[-1]["accuracy"],
        "total_epochs": epochs,
    }

    print(
        f"Test trainer completed: final_accuracy={final_metrics['final_accuracy']:.3f}"
    )

    return {
        "metrics": final_metrics,
        "artifacts": {"metrics_file": str(metrics_file), "model_file": str(model_file)},
    }
