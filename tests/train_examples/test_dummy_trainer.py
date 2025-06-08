import json
import os

from dr_exp.training.dummy_trainer import train
from dr_exp.logging.structured_logger import StructuredLogger


def make_cfg(tmp_path, num_epochs=4):
    return {
        "train": {"num_epochs": num_epochs},
        "log_dir": str(tmp_path / "logs"),
    }


def test_train_runs_and_logs(tmp_path):
    cfg = make_cfg(tmp_path, num_epochs=4)
    logger = StructuredLogger(cfg["log_dir"])
    result = train(cfg, logger)

    assert result.status == "success"
    assert os.path.exists(logger.paths.metrics_path)

    with open(logger.paths.metrics_path, "r") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 4
    assert all("epoch" in m for m in lines)

    assert os.path.isdir(logger.paths.checkpoint_dir)
    checkpoints = list(os.listdir(logger.paths.checkpoint_dir))
    assert len(checkpoints) == result.num_checkpoints

    artifact_file = os.path.join(logger.paths.artifact_dir, "loss_plot.txt")
    assert os.path.exists(artifact_file)

    # Ensure result attributes are present
    assert hasattr(result, "final_val_acc")
    assert hasattr(result, "final_train_loss")
    assert hasattr(result, "num_epochs")
    assert hasattr(result, "status")
    assert hasattr(result, "metrics_path")
    assert hasattr(result, "artifacts_path")
    assert hasattr(result, "num_checkpoints")


class ObjCfg:
    def __init__(self, tmp_path, num_epochs: int) -> None:
        self.train = {"num_epochs": num_epochs}
        self.log_dir = str(tmp_path / "logs")


def test_train_with_obj_cfg_and_default_logger(tmp_path):
    cfg = ObjCfg(tmp_path, 2)
    result = train(cfg)

    assert result.status == "success"
    assert result.num_epochs == 2
    # The default logger in train() should create logs in cfg.log_dir
    metrics_path = os.path.join(cfg.log_dir, "metrics.jsonl")
    assert os.path.exists(metrics_path)
    with open(metrics_path, "r") as f:
        lines = f.readlines()
    assert len(lines) == 2
