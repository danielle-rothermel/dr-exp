import time
from typing import Any, Dict, Optional

import torch
from omegaconf import OmegaConf
import deconcnn

from dr_exp.logging.base_logger import BaseLogger
from dr_exp.logging.structured_logger import StructuredLogger
from dr_exp.training.result import (
    TrainingResult,
    create_success_result,
    create_failure_result,
)


def validate_and_extract_decon_config(dr_exp_cfg: Any) -> OmegaConf:
    """Extract and validate deconCNN config from dr_exp wrapper.

    Uses deconCNN's own validation functions to ensure config correctness.
    Fails fast if any required deconCNN fields are missing or invalid.

    Parameters
    ----------
    dr_exp_cfg : Any
        Configuration from dr_exp (dict or object)

    Returns
    -------
    OmegaConf
        Validated configuration in deconCNN's expected format

    Raises
    ------
    ValueError
        If any required deconCNN config fields are missing or invalid
    """
    # Extract from dr_exp wrapper (if wrapped) or use directly
    if isinstance(dr_exp_cfg, dict) and "config" in dr_exp_cfg:
        config_dict = dr_exp_cfg["config"]  # Handle wrapped format from dr_exp
    else:
        config_dict = dr_exp_cfg  # Handle direct format

    # Convert to OmegaConf for deconCNN compatibility
    decon_cfg = OmegaConf.create(config_dict)

    # Ensure basic structure exists before detailed validation
    required_top_level = ["model", "optim", "lrsched", "data", "machine", "paths"]
    missing_top_level = [f for f in required_top_level if f not in decon_cfg]
    if missing_top_level:
        raise ValueError(
            f"Missing required top-level config sections: {missing_top_level}\n"
            f"Config must include sections: {required_top_level}\n"
            f"Use Hydra config composition to provide complete configurations."
        )

    # Use deconCNN's own validation functions - these will fail fast with detailed errors
    try:
        # Validate model configuration
        model_dict = OmegaConf.to_container(decon_cfg.model, resolve=True)
        deconcnn.validate_model_config(model_dict)

        # Validate optimizer configuration
        optim_dict = OmegaConf.to_container(decon_cfg.optim, resolve=True)
        deconcnn.validate_optimizer_config(optim_dict)

        # Validate scheduler configuration
        lrsched_dict = OmegaConf.to_container(decon_cfg.lrsched, resolve=True)
        deconcnn.validate_scheduler_config(lrsched_dict)

        # Validate training configuration (epochs, batch_size, etc.)
        training_dict = OmegaConf.to_container(decon_cfg, resolve=True)
        deconcnn.validate_training_config(training_dict)

    except Exception as e:
        raise ValueError(f"deconCNN config validation failed: {str(e)}")

    return decon_cfg


class DrExpClassificationModule:
    """Wrapper around deconCNN's ClassificationModule that logs to dr_exp's StructuredLogger."""

    def __init__(self, decon_module, dr_exp_logger: BaseLogger):
        self.decon_module = decon_module
        self.dr_exp_logger = dr_exp_logger
        self.final_metrics = {}
        self.logged_epochs = set()  # Track which epochs we've already logged

        # Replace the original on_validation_epoch_end method
        self._wrap_validation_epoch_end()

    def _wrap_validation_epoch_end(self):
        """Wrap the validation epoch end to capture and log metrics."""
        original_method = self.decon_module.on_validation_epoch_end

        def wrapped_on_validation_epoch_end():
            # Call the original method first
            original_method()

            current_epoch = self.decon_module.current_epoch

            # Get metrics from trainer.logged_metrics
            if hasattr(self.decon_module.trainer, "logged_metrics"):
                logged_metrics = self.decon_module.trainer.logged_metrics

                if logged_metrics:
                    # Convert tensor metrics to floats
                    epoch_metrics = {}
                    for key, value in logged_metrics.items():
                        if value is not None:
                            if torch.is_tensor(value):
                                epoch_metrics[key] = value.item()
                            else:
                                epoch_metrics[key] = float(value)

                    # Only log if we have both training and validation metrics (complete epoch)
                    # OR if this is epoch 0 and we have validation metrics (initial validation)
                    has_train_metrics = (
                        "train_loss" in epoch_metrics and "train_acc" in epoch_metrics
                    )
                    has_val_metrics = (
                        "val_loss" in epoch_metrics and "val_acc" in epoch_metrics
                    )

                    should_log = False

                    if (
                        current_epoch == 0
                        and has_val_metrics
                        and current_epoch not in self.logged_epochs
                    ):
                        # Log initial validation (epoch 0) once
                        should_log = True
                    elif (
                        current_epoch > 0
                        and has_train_metrics
                        and has_val_metrics
                        and current_epoch not in self.logged_epochs
                    ):
                        # Log complete epochs (with both training and validation)
                        should_log = True

                    if should_log:
                        # Add epoch information and log reason
                        epoch_metrics["epoch"] = current_epoch

                        # Log to dr_exp StructuredLogger
                        self.dr_exp_logger.log(epoch_metrics)

                        # Mark this epoch as logged
                        self.logged_epochs.add(current_epoch)

                        # Store as final metrics (will be overwritten each epoch)
                        self.final_metrics = {
                            "final_train_loss": epoch_metrics.get("train_loss"),
                            "final_train_acc": epoch_metrics.get("train_acc"),
                            "final_val_loss": epoch_metrics.get("val_loss"),
                            "final_val_acc": epoch_metrics.get("val_acc"),
                        }

        # Replace the method
        self.decon_module.on_validation_epoch_end = wrapped_on_validation_epoch_end

    def get_final_metrics(self) -> Dict[str, float]:
        """Get the final metrics from the last logged epoch."""
        # Remove None values and ensure all values are floats
        final_metrics = {}
        for key, value in self.final_metrics.items():
            if value is not None:
                final_metrics[key] = float(value)
        return final_metrics


def train_with_decon(
    cfg: Dict[str, Any], logger: Optional[BaseLogger] = None
) -> TrainingResult:
    """Training function for deconCNN integration (worker execution).

    This function expects a complete, pre-composed configuration from the JobDB.
    It does NOT handle Hydra composition - that should be done during upload.

    Parameters
    ----------
    cfg : Dict[str, Any]
        Complete deconCNN configuration (from JobDB)
    logger : BaseLogger, optional
        dr_exp's StructuredLogger for metrics/checkpoints

    Returns
    -------
    TrainingResult
        Structured result with all required training metrics and metadata.
    """
    # 1. Validate input - cfg is required for worker execution
    if cfg is None:
        return create_failure_result(
            error="cfg parameter is required for worker execution. Use scripts/upload_configs.py with --base-config-path=deconcnn_configs during upload step."
        )

    # 2. Setup logger - if this fails, we can't log anything
    if logger is None:
        try:
            log_dir = (
                cfg.get("log_dir", "./logs")
                if isinstance(cfg, dict)
                else getattr(cfg, "log_dir", "./logs")
            )
            logger = StructuredLogger(log_dir)
        except Exception as e:
            # No logger available, return basic failure info
            return create_failure_result(error=f"Failed to create logger: {str(e)}")

    # Now we have a guaranteed logger, so we can proceed with training
    try:
        # 3. Validate the provided config (should be complete from JobDB)
        decon_cfg = validate_and_extract_decon_config(cfg)

        # 4. Create deconCNN training components
        model, data_module, trainer = deconcnn.create_cifar10_training_components(
            decon_cfg
        )

        # 4. Wrap the Lightning module to log metrics to dr_exp
        dr_exp_module = DrExpClassificationModule(model, logger)

        # 5. Log initial configuration
        model_name = getattr(decon_cfg.model, "name", None) or getattr(
            decon_cfg.model, "architecture", "unknown"
        )
        logger.log(
            {
                "config_summary": {
                    "model_name": model_name,
                    "epochs": decon_cfg.epochs,
                    "batch_size": decon_cfg.batch_size,
                    "learning_rate": decon_cfg.optim.lr,
                    "device": decon_cfg.machine.device,
                }
            }
        )

        # 6. Run training with deconCNN
        initial_time = time.time()

        # Train the model using deconCNN's training function
        deconcnn.train_model(trainer, model, data_module, decon_cfg)

        training_time = time.time() - initial_time

        # 7. Get final metrics from our wrapper
        final_metrics = dr_exp_module.get_final_metrics()

        # 8. Log final summary metrics
        summary_metrics = {
            **final_metrics,
            "training_time_seconds": training_time,
            "num_epochs_completed": decon_cfg.epochs,
            "model_architecture": decon_cfg.model.architecture,
            "status": "success",
        }
        logger.log(summary_metrics)

        # 9. Finalize logger
        logger_meta = logger.finalize()

        # 10. Return standardized results
        return create_success_result(
            final_metrics=final_metrics,
            epochs=decon_cfg.epochs,
            logger_meta=logger_meta,
            artifacts_path=logger.paths.artifact_dir,
            training_time=training_time,
        )

    except Exception as e:
        # Handle any errors during training with detailed tracking
        import traceback

        error_msg = f"deconCNN training failed: {str(e)}"
        error_traceback = traceback.format_exc()

        # Logger is guaranteed to exist at this point
        logger.log(
            {"error": error_msg, "error_traceback": error_traceback, "status": "failed"}
        )
        logger_meta = logger.finalize()

        return create_failure_result(
            error=error_msg,
            metrics_path=logger_meta.get("metrics_path", ""),
            artifacts_path=logger.paths.artifact_dir,
            num_checkpoints=logger_meta.get("num_checkpoints", 0),
        )


# Alias for compatibility with dr_exp's expected interface
train = train_with_decon
