"""Dummy trainer for testing and smoke runs."""

import json
import random
import time
from pathlib import Path
from typing import Any


def train(
    job_id: str,
    worker_id: str,
    storage_path: str,
    epochs: int = 10,
    batch_size: int = 32,
    lr: float = 0.001,
    model: str = "resnet18",
    fail_rate: float = 0.0,
    **kwargs: Any,  # noqa: ANN401
) -> dict[str, Any]:
    """Dummy training function for testing."""
    storage = Path(storage_path)
    storage.mkdir(parents=True, exist_ok=True)

    config = {
        "epochs": epochs,
        "batch_size": batch_size,
        "lr": lr,
        "model": model,
        **kwargs,
    }
    (storage / "config.json").write_text(json.dumps(config, indent=2))

    print(f"Dummy trainer started: job_id={job_id}, model={model}, epochs={epochs}")

    if random.random() < fail_rate:  # noqa: S311
        raise RuntimeError(f"Simulated failure for job {job_id}")

    metrics_history = []
    for epoch in range(epochs):
        loss = 1.0 / (epoch + 1) + random.random() * 0.1  # noqa: S311
        accuracy = min(0.99, epoch / epochs + random.random() * 0.1)  # noqa: S311
        metrics_history.append({"epoch": epoch, "loss": loss, "accuracy": accuracy})
        time.sleep(0.01)

    final_metrics = metrics_history[-1] if metrics_history else {}
    (storage / "metrics.json").write_text(json.dumps(metrics_history, indent=2))

    model_file = storage / "model_final.pt"
    model_file.write_text(f"Dummy model {model} for job {job_id}")

    return {
        "status": "completed",
        "metrics": final_metrics,
        "epochs_completed": epochs,
        "model_path": str(model_file),
    }
