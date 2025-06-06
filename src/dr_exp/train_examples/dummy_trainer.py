import os
import time
from typing import Any, Dict, Optional

from dr_exp.logging.base_logger import BaseLogger
from dr_exp.logging.structured_logger import StructuredLogger


def train(cfg: Any, logger: Optional[BaseLogger] = None) -> Dict[str, Any]:
    """Simulate a training run and log metrics.

    Parameters
    ----------
    cfg : Any
        Configuration object for the run.
    logger : BaseLogger, optional
        Logger instance used to record metrics. If ``None`` a new logger is
        created.

    Returns
    -------
    dict[str, Any]
        Summary information about the run.
    """
    train_cfg = (
        cfg.get("train", {}) if isinstance(cfg, dict) else getattr(cfg, "train", {})
    )
    num_epochs = int(train_cfg.get("num_epochs", 10))

    if logger is None:
        # Get log_dir from config if available, otherwise use default
        log_dir = cfg.get("log_dir", "./logs") if isinstance(cfg, dict) else getattr(cfg, "log_dir", "./logs")
        logger = StructuredLogger(log_dir)

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

    # Create artifact in logger's artifact directory
    artifact_path = os.path.join(logger.paths.artifact_dir, "loss_plot.txt")
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
        "artifacts_path": logger.paths.artifact_dir,
        "num_checkpoints": logger_meta["num_checkpoints"],
    }
