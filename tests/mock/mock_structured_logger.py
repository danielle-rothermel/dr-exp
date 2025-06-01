import gzip
import json
import os
from datetime import datetime, UTC
from typing import Any, Dict, List


class StructuredLogger:
    """Simple logger for metrics, checkpoints, and artifacts."""

    def __init__(
        self, cfg: Any, compress_checkpoints: bool = False, debug: bool = False
    ) -> None:
        logging_cfg = (
            cfg.get("logging", {})
            if isinstance(cfg, dict)
            else getattr(cfg, "logging", {})
        )
        self.metrics_path = logging_cfg.get("out_path")
        self.checkpoint_dir = logging_cfg.get("checkpoint_dir")
        self.artifact_dir = logging_cfg.get("artifact_dir")

        if (
            self.metrics_path is None
            or self.checkpoint_dir is None
            or self.artifact_dir is None
        ):
            raise ValueError(
                "cfg.logging must define out_path, checkpoint_dir, and artifact_dir"
            )

        os.makedirs(os.path.dirname(self.metrics_path), exist_ok=True)
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        os.makedirs(self.artifact_dir, exist_ok=True)

        self.compress_checkpoints = compress_checkpoints
        self.debug = debug

        self._metrics_file = open(self.metrics_path, "a")
        self._num_metrics = 0
        self._num_checkpoints = 0
        self._artifact_paths: List[str] = []
        self._closed = False

    def log(self, metrics: Dict[str, Any]) -> None:
        entry = metrics.copy()
        entry["timestamp"] = datetime.now(UTC).isoformat() + "Z"
        self._metrics_file.write(json.dumps(entry) + "\n")
        self._metrics_file.flush()
        self._num_metrics += 1

    def save_checkpoint(self, state_dict: Dict[str, Any], tag: str) -> str:
        filename = f"checkpoint_{tag}.pt"
        if self.compress_checkpoints:
            filename += ".gz"
        path = os.path.join(self.checkpoint_dir, filename)

        if self.compress_checkpoints:
            with gzip.open(path, "wb") as f:
                f.write(json.dumps(state_dict).encode("utf-8"))
        else:
            with open(path, "w") as f:
                json.dump(state_dict, f)
        self._num_checkpoints += 1
        self._artifact_paths.append(path)
        return path

    def log_artifact(self, path: str) -> None:
        self._artifact_paths.append(path)

    def finalize(self) -> Dict[str, Any]:
        if not self._closed:
            self._metrics_file.close()
            self._closed = True
        return {
            "metrics_path": self.metrics_path,
            "num_metrics": self._num_metrics,
            "artifact_paths": self._artifact_paths,
            "num_checkpoints": self._num_checkpoints,
            "finalize_success": True,
        }
