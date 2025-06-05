"""Base class for structured logging implementations."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from .logger_paths import LoggerPathManager


class BaseLogger(ABC):
    """Abstract base class for structured logging implementations.
    
    This class defines the interface that all logger implementations must
    provide for metrics logging, checkpoint saving, artifact tracking, and
    finalization operations.
    """
    
    # Required attributes that subclasses must provide
    run_id: str
    
    @property
    @abstractmethod
    def paths(self) -> LoggerPathManager:
        """Get the path manager for this logger.
        
        Returns
        -------
        LoggerPathManager
            The path manager instance handling all file paths.
        """
        pass
    
    @abstractmethod
    def log(self, metrics: Dict[str, Any]) -> None:
        """Log metrics data.
        
        Parameters
        ----------
        metrics : dict[str, Any]
            Dictionary containing metrics to log. Common keys include
            'epoch', 'train_loss', 'val_acc', etc.
        """
        pass
    
    @abstractmethod
    def save_checkpoint(self, state_dict: Dict[str, Any], tag: str) -> str:
        """Save a model checkpoint.
        
        Parameters
        ----------
        state_dict : dict[str, Any]
            Serializable checkpoint data containing model state.
        tag : str
            Identifier for the checkpoint (e.g., 'epoch_10', 'best').
            
        Returns
        -------
        str
            Path to the saved checkpoint file.
        """
        pass
    
    @abstractmethod
    def log_artifact(self, path: str) -> None:
        """Register an artifact for tracking and potential upload.
        
        Parameters
        ----------
        path : str
            Path to the artifact file or directory to register.
        """
        pass
    
    @abstractmethod
    def finalize(self) -> Dict[str, Any]:
        """Finalize logging and return summary metadata.
        
        This method should close any open files, flush buffers, and
        return a summary of the logging session.
        
        Returns
        -------
        dict[str, Any]
            Summary metadata containing information about the logging
            session, such as metrics_path, num_metrics, artifact_paths,
            num_checkpoints, and finalize_success.
        """
        pass


__all__ = ["BaseLogger"]