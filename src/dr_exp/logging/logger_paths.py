"""Path management for the logging system."""

import os
from dataclasses import dataclass
from typing import Union


@dataclass
class LoggerPathConfig:
    """Configuration for logger file paths."""

    base_dir: str
    metrics_filename: str = "metrics.jsonl"
    checkpoint_dir: str = "checkpoints"
    artifact_dir: str = "artifacts"
    error_filename: str = "errors.log"


class LoggerPathManager:
    """Manages all file paths for the logger."""

    def __init__(self, config: Union[str, LoggerPathConfig]):
        """Initialize path manager with either a base directory or full config.

        Args:
            config: Either a string path to base directory or LoggerPathConfig object
        """
        if isinstance(config, str):
            config = LoggerPathConfig(base_dir=config)
        self.config = config
        self._setup_directories()

    def _setup_directories(self):
        """Create all necessary directories."""
        # Create base directory
        os.makedirs(self.config.base_dir, exist_ok=True)

        # Create subdirectories
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        os.makedirs(self.artifact_dir, exist_ok=True)

    @property
    def base_dir(self) -> str:
        """Get the base directory."""
        return self.config.base_dir

    @property
    def metrics_path(self) -> str:
        """Get the path to the metrics file."""
        return os.path.join(self.config.base_dir, self.config.metrics_filename)

    @property
    def checkpoint_dir(self) -> str:
        """Get the checkpoint directory."""
        return os.path.join(self.config.base_dir, self.config.checkpoint_dir)

    @property
    def artifact_dir(self) -> str:
        """Get the artifact directory."""
        return os.path.join(self.config.base_dir, self.config.artifact_dir)

    @property
    def error_log_path(self) -> str:
        """Get the path to the error log file."""
        return os.path.join(self.config.base_dir, self.config.error_filename)

    def checkpoint_path(self, tag: str, compressed: bool = False) -> str:
        """Get the path for a specific checkpoint file.

        Args:
            tag: Checkpoint identifier
            compressed: Whether the checkpoint will be gzipped

        Returns:
            Full path to checkpoint file
        """
        ext = ".pt.gz" if compressed else ".pt"
        return os.path.join(self.checkpoint_dir, f"checkpoint_{tag}{ext}")

    def artifact_path(self, filename: str) -> str:
        """Get the path for a specific artifact file.

        Args:
            filename: Name of the artifact file

        Returns:
            Full path to artifact file
        """
        return os.path.join(self.artifact_dir, filename)
