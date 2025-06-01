import json
import os
import gzip
import uuid
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

import fcntl


def _get_attr(obj: Any, key: str, default: Optional[Any] = None) -> Any:
    """Helper to get attribute or dict key from obj."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class StructuredLogger:
    """Local logger for metrics, checkpoints and artifacts."""

    def __init__(
        self, cfg: Any, compress_checkpoints: bool = False, debug: bool = False
    ) -> None:
        logging_cfg = cfg["logging"] if isinstance(cfg, dict) else cfg.logging
        self.out_path = _get_attr(logging_cfg, "out_path")
        self.artifact_dir = _get_attr(logging_cfg, "artifact_dir")
        self.checkpoint_dir = _get_attr(logging_cfg, "checkpoint_dir")
        self.log_file = _get_attr(logging_cfg, "log_file", None)

        self.compress_checkpoints = compress_checkpoints
        self.debug = debug
        self.run_id = getattr(cfg, "run_id", uuid.uuid4().hex)

        os.makedirs(os.path.dirname(self.out_path), exist_ok=True)
        os.makedirs(self.artifact_dir, exist_ok=True)
        os.makedirs(self.checkpoint_dir, exist_ok=True)

        self.error_log_path = os.path.join(
            os.path.dirname(self.out_path), "logger_error.log"
        )
        self.metrics_file = open(self.out_path, "a")
        self.metrics_count = 0
        self.checkpoint_count = 0
        self.artifact_paths: List[str] = []
        self._finalized = False

    def _write_error(self, msg: str) -> None:
        with open(self.error_log_path, "a") as ef:
            ef.write(f"{datetime.now(UTC).isoformat()}Z {msg}\n")

    def log(self, metrics: Dict[str, Any]) -> None:
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
        filename = f"checkpoint_{tag}.pt"
        if self.compress_checkpoints:
            filename += ".gz"
        path = os.path.join(self.checkpoint_dir, filename)
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
        if os.path.exists(path):
            self.artifact_paths.append(os.path.abspath(path))
        else:  # pragma: no cover - debug path
            if self.debug:
                raise FileNotFoundError(path)
            self._write_error(f"artifact not found: {path}")

    def _summary(self, success: bool) -> Dict[str, Any]:
        return {
            "metrics_path": self.out_path,
            "num_metrics": self.metrics_count,
            "artifact_paths": self.artifact_paths,
            "num_checkpoints": self.checkpoint_count,
            "finalize_success": success,
        }

    def finalize(self) -> Dict[str, Any]:
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
