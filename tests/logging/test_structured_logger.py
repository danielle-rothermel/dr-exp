import json
import os
import gzip
from multiprocessing import Process
import pytest
from pathlib import Path

from dr_exp.logging.structured_logger import StructuredLogger


def test_logger_basic(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "logs")
    logger = StructuredLogger(log_dir)

    logger.log({"epoch": 1, "loss": 0.5})
    logger.log({"epoch": 2, "loss": 0.4})

    ckpt_path = logger.save_checkpoint({"weights": [1, 2]}, "ep2")
    assert os.path.exists(ckpt_path)

    artifact_file = tmp_path / "plot.png"
    artifact_file.write_text("data")
    logger.log_artifact(str(artifact_file))

    summary = logger.finalize()
    assert summary["num_metrics"] == 2
    assert summary["num_checkpoints"] == 1
    assert summary["artifact_paths"] == [os.path.abspath(artifact_file)]

    with open(logger.paths.metrics_path) as f:
        lines = f.readlines()
    assert len(lines) == 2
    for line in lines:
        data = line.strip()
        assert data.startswith("{") and data.endswith("}")


def _worker(log_dir: str, count: int) -> None:
    logger = StructuredLogger(log_dir)
    for i in range(count):
        logger.log({"i": i})
    logger.finalize()


def test_logger_concurrent(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "logs")

    procs = [Process(target=_worker, args=(log_dir, 10)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()

    with open(os.path.join(log_dir, "metrics.jsonl"), "r") as f:
        lines = f.readlines()
    assert len(lines) == 40


def test_checkpoint_compression(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "logs")
    logger = StructuredLogger(log_dir, compress_checkpoints=True)
    state = {"a": 1}
    ckpt_path = logger.save_checkpoint(state, "t1")
    assert ckpt_path.endswith(".gz")
    with gzip.open(ckpt_path, "rb") as f:
        data = json.loads(f.read().decode("utf-8"))
    assert data == state
    logger.finalize()


def test_error_log_non_debug(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "logs")
    logger = StructuredLogger(log_dir)
    # After assert refactor, missing artifacts now raise AssertionError regardless of debug mode
    with pytest.raises(AssertionError, match="Artifact path does not exist"):
        logger.log_artifact(str(tmp_path / "missing.txt"))


def test_debug_mode_raises(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "logs")
    logger = StructuredLogger(log_dir, debug=True)
    with pytest.raises(AssertionError):
        logger.log_artifact(str(tmp_path / "missing.txt"))


def test_finalize_idempotent(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "logs")
    logger = StructuredLogger(log_dir)
    logger.log({"a": 1})
    first = logger.finalize()
    second = logger.finalize()
    assert first == second
