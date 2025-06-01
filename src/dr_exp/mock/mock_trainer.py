import os
import time
from typing import Any, Dict, Optional

from tests.mock.mock_structured_logger import StructuredLogger


def train(cfg: Any, logger: Optional[StructuredLogger] = None) -> Dict[str, Any]:
    """Simulate a training run using StructuredLogger."""
    train_cfg = (
        cfg.get("train", {}) if isinstance(cfg, dict) else getattr(cfg, "train", {})
    )
    num_epochs = int(train_cfg.get("num_epochs", 10))

    if logger is None:
        logger = StructuredLogger(cfg)

    final_train_loss = 0.0
    final_val_acc = 0.0
    for epoch in range(1, num_epochs + 1):
        time.sleep(0.01)
        train_loss = round(1.0 / (epoch + 1), 3)
        val_acc = round(0.5 + epoch * 0.05, 3)
        logger.log({"epoch": epoch, "train_loss": train_loss, "val_acc": val_acc})
        final_train_loss = train_loss
        final_val_acc = val_acc

        if epoch in {num_epochs // 2, num_epochs}:
            logger.save_checkpoint({"epoch": epoch}, tag=f"epoch_{epoch}")

    artifact_path = os.path.join(cfg["logging"]["artifact_dir"], "loss_plot.txt")
    with open(artifact_path, "w") as f:
        f.write("dummy artifact")
    logger.log_artifact(artifact_path)

    logger_meta = logger.finalize()

    return {
        "final_val_acc": final_val_acc,
        "final_train_loss": final_train_loss,
        "num_epochs": num_epochs,
        "status": "success",
        "metrics_path": logger_meta["metrics_path"],
        "artifacts_path": cfg["logging"]["artifact_dir"],
        "num_checkpoints": logger_meta["num_checkpoints"],
    }
