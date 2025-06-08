import os
import time
from typing import Any, Dict, Optional

import torch
from omegaconf import OmegaConf
import deconcnn

from dr_exp.logging.base_logger import BaseLogger
from dr_exp.logging.structured_logger import StructuredLogger
from dr_exp.training.result import TrainingResult, create_success_result, create_failure_result


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


def extract_validation_metrics_from_trainer(trainer, logger: BaseLogger) -> Dict[str, float]:
    """Extract validation metrics from Lightning trainer.
    
    Validation metrics should be reliably available in logged_metrics.
    
    Parameters
    ----------
    trainer : Lightning trainer
        Trained Lightning trainer with logged metrics
    logger : BaseLogger
        Logger for recording extraction details
        
    Returns
    -------
    Dict[str, float]
        Dictionary with validation metrics: final_val_acc, final_val_loss
        
    Raises
    ------
    ValueError
        If validation metrics cannot be extracted
    """
    # Fail immediately if trainer doesn't have logged metrics
    if not hasattr(trainer, 'logged_metrics'):
        raise ValueError("Lightning trainer has no 'logged_metrics' attribute - training may have failed")
    
    logged_metrics = trainer.logged_metrics
    if not logged_metrics:
        raise ValueError("Lightning trainer.logged_metrics is empty - no metrics were recorded during training")
    
    available_keys = list(logged_metrics.keys())
    
    # Get validation metrics from logged_metrics (these should be reliably available)
    val_acc = logged_metrics.get("val_acc") or logged_metrics.get("val_acc_epoch") 
    val_loss = logged_metrics.get("val_loss") or logged_metrics.get("val_loss_epoch")
    
    # Fail if any required validation metric is missing  
    if val_acc is None:
        raise ValueError(f"Required metric 'val_acc' not found. Available keys: {available_keys}")
        
    if val_loss is None:
        raise ValueError(f"Required metric 'val_loss' not found. Available keys: {available_keys}")
    
    # Convert to float and validate values - fail if invalid
    try:
        val_acc_float = float(val_acc) 
        val_loss_float = float(val_loss)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Failed to convert validation metrics to float: {e}")
    
    # Check for infinite or NaN values - fail if found
    if not torch.isfinite(torch.tensor(val_acc_float)):
        raise ValueError(f"val_acc is not finite: {val_acc_float}")
    if not torch.isfinite(torch.tensor(val_loss_float)):
        raise ValueError(f"val_loss is not finite: {val_loss_float}")
    
    return {
        "final_val_acc": val_acc_float,
        "final_val_loss": val_loss_float
    }


def extract_training_metrics_from_csv(trainer, logger: BaseLogger) -> Dict[str, float]:
    """Extract training metrics from Lightning's automatically logged CSV file.
    
    This is more efficient than recalculating metrics on every batch.
    Lightning automatically logs training metrics to metrics.csv in real-time.
    
    Parameters
    ----------
    trainer : Lightning trainer
        Trained Lightning trainer
    logger : BaseLogger
        Logger for recording extraction details
        
    Returns
    -------
    Dict[str, float]
        Dictionary with training metrics: final_train_loss, final_train_acc
        
    Raises
    ------
    ValueError
        If CSV file cannot be found or training metrics are missing
    """
    import pandas as pd
    import os
    
    # Find the Lightning CSV metrics file
    # Lightning saves to {default_root_dir}/lightning_logs/version_0/metrics.csv
    if hasattr(trainer, 'log_dir') and trainer.log_dir:
        csv_path = os.path.join(trainer.log_dir, "metrics.csv")
    else:
        # Fallback: check if trainer has default_root_dir
        if hasattr(trainer, 'default_root_dir') and trainer.default_root_dir:
            csv_path = os.path.join(trainer.default_root_dir, "lightning_logs", "version_0", "metrics.csv")
        else:
            raise ValueError("Cannot determine Lightning CSV metrics file location")
    
    if not os.path.exists(csv_path):
        raise ValueError(f"Lightning metrics CSV file not found at: {csv_path}")
    
    try:
        # Read the CSV file
        df = pd.read_csv(csv_path)
        
        # Filter to rows that have training metrics (train_loss and train_acc are not NaN)
        train_rows = df.dropna(subset=['train_loss', 'train_acc'])
        
        if train_rows.empty:
            raise ValueError("No training metrics found in Lightning CSV file")
        
        # Get the final (last) training metrics
        final_row = train_rows.iloc[-1]
        final_train_loss = float(final_row['train_loss'])
        final_train_acc = float(final_row['train_acc'])
        
        # Validate the metrics
        if not torch.isfinite(torch.tensor(final_train_loss)):
            raise ValueError(f"final_train_loss is not finite: {final_train_loss}")
        if not torch.isfinite(torch.tensor(final_train_acc)):
            raise ValueError(f"final_train_acc is not finite: {final_train_acc}")
        
        return {
            "final_train_loss": final_train_loss,
            "final_train_acc": final_train_acc
        }
        
    except Exception as e:
        raise ValueError(f"Failed to extract training metrics from CSV {csv_path}: {str(e)}")


class DrExpLoggerAdapter:
    """Adapter to capture metrics from Lightning training and forward to dr_exp StructuredLogger."""
    
    def __init__(self, dr_exp_logger: BaseLogger):
        self.dr_exp_logger = dr_exp_logger
        self.current_epoch = 0
        self.epoch_metrics = {}
        
    def log_metrics(self, metrics: Dict[str, Any], step: Optional[int] = None):
        """Log metrics to dr_exp logger."""
        # Filter out None values and convert tensors to scalars
        clean_metrics = {}
        for key, value in metrics.items():
            if value is not None:
                if torch.is_tensor(value):
                    clean_metrics[key] = value.item()
                else:
                    clean_metrics[key] = value
        
        # Add step information
        if step is not None:
            clean_metrics["step"] = step
            
        # Log to dr_exp
        self.dr_exp_logger.log(clean_metrics)


def train_with_decon(cfg: Any, logger: Optional[BaseLogger] = None) -> TrainingResult:
    """Training function integrating deconCNN with dr_exp.
    
    Parameters
    ----------
    cfg : Any
        Training configuration (unwrapped, native format from dr_exp)
    logger : BaseLogger, optional
        dr_exp's StructuredLogger for metrics/checkpoints
        
    Returns
    -------
    TrainingResult
        Structured result with all required training metrics and metadata.
    """
    # 1. Setup logger first - if this fails, we can't log anything
    if logger is None:
        try:
            log_dir = cfg.get("log_dir", "./logs") if isinstance(cfg, dict) else getattr(cfg, "log_dir", "./logs")
            logger = StructuredLogger(log_dir)
        except Exception as e:
            # No logger available, return basic failure info
            return create_failure_result(
                error=f"Failed to create logger: {str(e)}"
            )
    
    # Now we have a guaranteed logger, so we can proceed with training
    try:
        
        # 2. Validate and extract config format
        decon_cfg = validate_and_extract_decon_config(cfg)
        
        # 3. Create deconCNN training components
        model, data_module, trainer = deconcnn.create_cifar10_training_components(decon_cfg)
        
        # 4. Setup logging adapter
        logging_adapter = DrExpLoggerAdapter(logger)
        
        # 5. Log initial configuration
        logger.log({
            "config_summary": {
                "model_name": decon_cfg.model.name,
                "epochs": decon_cfg.epochs,
                "batch_size": decon_cfg.batch_size,
                "learning_rate": decon_cfg.optim.lr,
                "device": decon_cfg.machine.device
            }
        })
        
        # 6. Run training with deconCNN
        initial_time = time.time()
        
        # Train the model using deconCNN's training function
        deconcnn.train_model(trainer, model, data_module, decon_cfg)
        
        training_time = time.time() - initial_time
        
        # 7. Extract final metrics - use Lightning's CSV file for training metrics
        validation_metrics = extract_validation_metrics_from_trainer(trainer, logger)
        training_metrics = extract_training_metrics_from_csv(trainer, logger)
        
        # Combine training and validation metrics
        final_metrics = {
            **training_metrics,
            **validation_metrics
        }
        
        # 8. Log final summary metrics
        summary_metrics = {
            **final_metrics,
            "training_time_seconds": training_time,
            "num_epochs_completed": decon_cfg.epochs,
            "model_architecture": decon_cfg.model.architecture,
            "status": "success"
        }
        logger.log(summary_metrics)
        
        # 9. Save model checkpoint if training completed successfully
        if hasattr(model, 'state_dict'):
            logger.save_checkpoint({
                "model_state_dict": model.state_dict(),
                "config": decon_cfg,
                "final_metrics": final_metrics
            }, tag="final_model")
        
        # 10. Finalize logger
        logger_meta = logger.finalize()
        
        # 11. Return standardized results
        return create_success_result(
            final_metrics=final_metrics,
            epochs=decon_cfg.epochs,
            logger_meta=logger_meta,
            artifacts_path=logger.paths.artifact_dir,
            training_time=training_time
        )
        
    except Exception as e:
        # Handle any errors during training with detailed tracking
        import traceback
        error_msg = f"deconCNN training failed: {str(e)}"
        error_traceback = traceback.format_exc()
        
        # Logger is guaranteed to exist at this point
        logger.log({
            "error": error_msg, 
            "error_traceback": error_traceback,
            "status": "failed"
        })
        logger_meta = logger.finalize()
        
        return create_failure_result(
            error=error_msg,
            metrics_path=logger_meta.get("metrics_path", ""),
            artifacts_path=logger.paths.artifact_dir,
            num_checkpoints=logger_meta.get("num_checkpoints", 0)
        )


# Alias for compatibility with dr_exp's expected interface
train = train_with_decon