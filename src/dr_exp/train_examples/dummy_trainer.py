import os
import time
from typing import Any, Optional

from dr_exp.logging.base_logger import BaseLogger
from dr_exp.logging.structured_logger import StructuredLogger
from dr_exp.training.result import TrainingResult, create_success_result


def train(cfg: Any, logger: Optional[BaseLogger] = None) -> TrainingResult:
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
    TrainingResult
        Summary information about the run.
    """
    # Extract num_epochs from config - check multiple possible locations for compatibility
    num_epochs = 10  # default
    if isinstance(cfg, dict):
        # Try top-level fields first (for dr_exp wrapped configs)
        num_epochs = cfg.get("max_epochs", cfg.get("epochs", num_epochs))
        # Check nested train config (for direct test calls and backwards compatibility)
        train_cfg = cfg.get("train", {})
        if "num_epochs" in train_cfg:
            num_epochs = train_cfg["num_epochs"]  # Override with nested value if present
    else:
        # Handle object-style configs
        num_epochs = getattr(cfg, "max_epochs", getattr(cfg, "epochs", num_epochs))
        # Check nested train attribute
        if hasattr(cfg, "train") and isinstance(cfg.train, dict) and "num_epochs" in cfg.train:
            num_epochs = cfg.train["num_epochs"]
    
    num_epochs = int(num_epochs)

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

    final_metrics = {
        "final_val_acc": final_val_acc,
        "final_train_loss": final_train_loss,
        "final_val_loss": final_train_loss  # Use train loss as val loss for dummy
    }
    
    return create_success_result(
        final_metrics=final_metrics,
        epochs=num_epochs,
        logger_meta=logger_meta,
        artifacts_path=logger.paths.artifact_dir,
        training_time=0.1  # Dummy training time
    )
