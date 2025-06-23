"""Structured logging for ML experiments."""

import json
from pathlib import Path
from typing import Any
from datetime import datetime, UTC
from contextlib import contextmanager

from omegaconf import OmegaConf, DictConfig


def _convert_config(config: Any) -> Any:  # noqa: ANN401
    """Convert DictConfig and other special objects to JSON-serializable types."""
    if isinstance(config, DictConfig):
        return OmegaConf.to_container(config, resolve=True)
    elif isinstance(config, dict):
        return {k: _convert_config(v) for k, v in config.items()}
    elif isinstance(config, list | tuple):
        return [_convert_config(item) for item in config]
    else:
        return config


class StructuredLogger:
    """Logger that writes structured data (metrics, configs, etc.) to files."""

    def __init__(self, log_dir: str | Path, job_id: str, worker_id: str) -> None:
        """Initialize structured logger.

        Args:
            log_dir: Directory to write logs to
            job_id: Job ID for this run
            worker_id: Worker ID running this job
        """
        self.log_dir = Path(log_dir)
        self.job_id = job_id
        self.worker_id = worker_id

        # Ensure directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # File paths
        self.metrics_file = self.log_dir / "metrics.jsonl"
        self.config_file = self.log_dir / "config.json"
        self.metadata_file = self.log_dir / "metadata.json"
        self.events_file = self.log_dir / "events.jsonl"

        # Write initial metadata
        self._write_metadata()

    def _write_metadata(self) -> None:
        """Write job metadata."""
        metadata = {
            "job_id": self.job_id,
            "worker_id": self.worker_id,
            "started_at": datetime.now(UTC).isoformat(),
            "log_version": "1.0",
        }

        with self.metadata_file.open("w") as f:
            json.dump(metadata, f, indent=2)

    def log_config(self, config: dict[str, Any]) -> None:
        """Log the configuration used for this run.

        Args:
            config: Configuration dictionary
        """
        # Convert DictConfig to regular dict if needed
        config = _convert_config(config)

        with self.config_file.open("w") as f:
            json.dump(config, f, indent=2)

    def log_metrics(self, metrics: dict[str, Any], step: int | None = None) -> None:
        """Log metrics for a training step.

        Args:
            metrics: Dictionary of metric values
            step: Optional step number (epoch, iteration, etc.)
        """
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "step": step,
            "metrics": metrics,
        }

        with self.metrics_file.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def log_event(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Log a training event (start, end, checkpoint, etc.).

        Args:
            event_type: Type of event
            data: Optional event data
        """
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "data": data or {},
        }

        with self.events_file.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def log_artifact(
        self,
        artifact_path: Path,
        artifact_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log that an artifact was created.

        Args:
            artifact_path: Path to the artifact
            artifact_type: Type of artifact (model, plot, etc.)
            metadata: Optional metadata about the artifact
        """
        self.log_event(
            "artifact_created",
            {
                "path": str(artifact_path),
                "type": artifact_type,
                "metadata": metadata or {},
            },
        )

    @contextmanager
    def phase(self, phase_name: str) -> Any:  # noqa: ANN401
        """Context manager for logging training phases.

        Args:
            phase_name: Name of the phase (train, eval, etc.)
        """
        self.log_event(f"{phase_name}_start")
        try:
            yield
        finally:
            self.log_event(f"{phase_name}_end")

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the logged data.

        Returns:
            Summary dictionary
        """
        summary = {
            "job_id": self.job_id,
            "worker_id": self.worker_id,
            "metrics_entries": 0,
            "events_entries": 0,
            "final_metrics": None,
        }

        # Count metrics entries and get final
        if self.metrics_file.exists():
            with self.metrics_file.open() as f:
                lines = f.readlines()
                summary["metrics_entries"] = len(lines)
                if lines:
                    last_entry = json.loads(lines[-1])
                    summary["final_metrics"] = last_entry.get("metrics", {})

        # Count events
        if self.events_file.exists():
            with self.events_file.open() as f:
                summary["events_entries"] = sum(1 for _ in f)

        return summary
