import json
import os
import gzip
import uuid
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Union

import fcntl

from .base_logger import BaseLogger
from .logger_paths import LoggerPathConfig, LoggerPathManager


class StructuredLogger(BaseLogger):
    """Local filesystem-based structured logger implementation.

    This class provides a concrete implementation of the BaseLogger interface
    using local files for metrics storage, checkpoint saving, and artifact
    tracking. Ideal for development, testing, and local training runs."""

    def __init__(
        self,
        log_dir: Union[str, LoggerPathConfig],
        run_id: Optional[str] = None,
        compress_checkpoints: bool = False,
        debug: bool = False,
    ) -> None:
        """Initialize the structured logger.

        Creates necessary directories and opens the metrics file for writing.

        Parameters
        ----------
        log_dir : str or LoggerPathConfig
            Base directory for all logging outputs, or a full path configuration.
        run_id : str, optional
            Unique identifier for this run. If not provided, a UUID will be generated.
        compress_checkpoints : bool, optional
            Whether to gzip checkpoint files for space efficiency, by default False.
        debug : bool, optional
            If True, errors are raised immediately instead of being logged
            to an error file. Useful for development, by default False.
        """
        self._paths = LoggerPathManager(log_dir)
        self.compress_checkpoints = compress_checkpoints
        self.debug = debug
        self.run_id = run_id or uuid.uuid4().hex

        self.metrics_file = open(self._paths.metrics_path, "a", encoding="utf-8")
        self.metrics_count = 0
        self.checkpoint_count = 0
        self.artifact_paths: List[str] = []
        self._finalized = False

    @property
    def paths(self) -> LoggerPathManager:
        """Get the path manager for this logger."""
        return self._paths

    def _write_error(self, msg: str) -> None:
        """Append an error message to the logger error file."""
        with open(self._paths.error_log_path, "a", encoding="utf-8") as ef:
            ef.write(f"{datetime.now(UTC).isoformat()}Z {msg}\n")

    def log(self, metrics: Dict[str, Any]) -> None:
        """Log metrics data to the metrics file.

        Writes metrics as a JSON line to the configured output file with
        file locking for thread safety. Automatically adds run_id and
        timestamp if not present.

        Parameters
        ----------
        metrics : dict[str, Any]
            Dictionary containing metrics to log. Common keys include
            'epoch', 'train_loss', 'val_acc', etc.
        """
        record = dict(metrics)
        record.setdefault("run_id", self.run_id)
        record.setdefault("timestamp", datetime.now(UTC).isoformat() + "Z")
        try:
            fcntl.flock(self.metrics_file.fileno(), fcntl.LOCK_EX)
            self.metrics_file.write(json.dumps(record) + "\n")
            self.metrics_file.flush()
            self.metrics_count += 1
        except Exception as e:  # pragma: no cover - debug path
            if self.debug:
                raise
            self._write_error(f"log error: {e}")
        finally:
            try:
                fcntl.flock(self.metrics_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass

    def save_checkpoint(self, state_dict: Dict[str, Any], tag: str) -> str:
        """Save a model checkpoint to the checkpoint directory.

        Saves checkpoint data as JSON, optionally compressed with gzip.
        Filenames follow the pattern 'checkpoint_{tag}.pt[.gz]'.

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
        path = self._paths.checkpoint_path(tag, compressed=self.compress_checkpoints)
        try:
            if self.compress_checkpoints:
                with gzip.open(path, "wb") as f:
                    f.write(json.dumps(state_dict).encode("utf-8"))
            else:
                with open(path, "w") as f:
                    json.dump(state_dict, f)
            self.checkpoint_count += 1
        except Exception as e:  # pragma: no cover - debug path
            if self.debug:
                raise
            self._write_error(f"checkpoint error: {e}")
        return path

    def log_artifact(self, path: str) -> None:
        """Register an artifact file for tracking and potential upload.

        Adds the absolute path to the internal artifact list if the file exists.
        Artifact paths are included in the finalization summary.

        Parameters
        ----------
        path : str
            Path to the artifact file or directory to register.
        """
        if os.path.exists(path):
            self.artifact_paths.append(os.path.abspath(path))
        else:  # pragma: no cover - debug path
            if self.debug:
                raise FileNotFoundError(path)
            self._write_error(f"artifact not found: {path}")

    def _summary(self, success: bool) -> Dict[str, Any]:
        """Return a final summary dictionary."""
        return {
            "metrics_path": self._paths.metrics_path,
            "num_metrics": self.metrics_count,
            "artifact_paths": self.artifact_paths,
            "num_checkpoints": self.checkpoint_count,
            "finalize_success": success,
        }

    def finalize(self) -> Dict[str, Any]:
        """Finalize logging and return summary metadata.

        Closes the metrics file and returns comprehensive metadata about
        the logging session. This method is idempotent and can be called
        multiple times safely.

        Returns
        -------
        dict[str, Any]
            Summary metadata containing:
            - metrics_path: path to the metrics file
            - num_metrics: number of metrics logged
            - artifact_paths: list of registered artifact paths
            - num_checkpoints: number of checkpoints saved
            - finalize_success: whether finalization succeeded
        """
        if self._finalized:
            return self._summary(True)
        finalize_success = True
        try:
            self.metrics_file.flush()
            self.metrics_file.close()
        except Exception as e:  # pragma: no cover - debug path
            finalize_success = False
            if self.debug:
                raise
            self._write_error(f"finalize error: {e}")
        self._finalized = True
        return self._summary(finalize_success)
