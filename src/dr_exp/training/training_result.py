"""Training result types and factory functions."""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TrainingResult:
    """Required return type for all training functions. No exceptions.

    This dataclass enforces a strict contract for training function returns.
    All fields are required and validated on creation to ensure the system
    fails fast and loud if expectations are not met.
    """

    status: str  # Must be "success" or "failed"
    final_val_acc: float
    final_train_loss: float
    num_epochs: int
    metrics_path: str
    artifacts_path: str
    num_checkpoints: int
    final_val_loss: float
    training_time: float
    error: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate fields immediately on creation to fail fast."""
        if self.status not in ["success", "failed"]:
            raise ValueError(
                f"status must be 'success' or 'failed', got: {self.status}"
            )
        if self.status == "failed" and self.error is None:
            raise ValueError("error field is required when status='failed'")
        if self.status == "success" and self.error is not None:
            raise ValueError("error field must be None when status='success'")
        if self.num_epochs < 0:
            raise ValueError(f"num_epochs must be non-negative, got: {self.num_epochs}")
        if self.num_checkpoints < 0:
            raise ValueError(
                f"num_checkpoints must be non-negative, got: {self.num_checkpoints}"
            )


def create_success_result(
    final_metrics: Dict[str, float],
    epochs: int,
    logger_meta: Dict[str, Any],
    artifacts_path: str,
    training_time: float,
) -> TrainingResult:
    """Factory for success results - all parameters required.

    This function will fail with KeyError if any required fields are missing
    from final_metrics or logger_meta, enforcing complete data.

    Parameters
    ----------
    final_metrics : Dict[str, float]
        Must contain: final_val_acc, final_train_loss, final_val_loss
    epochs : int
        Number of epochs completed
    logger_meta : Dict[str, Any]
        Must contain: metrics_path, num_checkpoints
    artifacts_path : str
        Path to artifacts directory
    training_time : float
        Training time in seconds

    Returns
    -------
    TrainingResult
        Validated success result

    Raises
    ------
    KeyError
        If any required fields are missing from input dicts
    """
    return TrainingResult(
        status="success",
        final_val_acc=final_metrics["final_val_acc"],  # Will KeyError if missing
        final_train_loss=final_metrics["final_train_loss"],
        final_val_loss=final_metrics["final_val_loss"],
        num_epochs=epochs,
        metrics_path=logger_meta["metrics_path"],  # Will KeyError if missing
        artifacts_path=artifacts_path,
        num_checkpoints=logger_meta["num_checkpoints"],
        training_time=training_time,
        error=None,
    )


def create_failure_result(
    error: str,
    epochs: int = 0,
    metrics_path: str = "",
    artifacts_path: str = "",
    num_checkpoints: int = 0,
    training_time: float = 0.0,
) -> TrainingResult:
    """Factory for failure results - error required, rest have sensible defaults.

    Parameters
    ----------
    error : str
        Required error message describing the failure
    epochs : int, optional
        Number of epochs completed before failure, by default 0
    metrics_path : str, optional
        Path to metrics file, by default ""
    artifacts_path : str, optional
        Path to artifacts directory, by default ""
    num_checkpoints : int, optional
        Number of checkpoints saved, by default 0
    training_time : float, optional
        Training time before failure, by default 0.0

    Returns
    -------
    TrainingResult
        Validated failure result
    """
    return TrainingResult(
        status="failed",
        error=error,
        final_val_acc=0.0,
        final_train_loss=float("inf"),
        final_val_loss=float("inf"),
        num_epochs=epochs,
        metrics_path=metrics_path,
        artifacts_path=artifacts_path,
        num_checkpoints=num_checkpoints,
        training_time=training_time,
    )
