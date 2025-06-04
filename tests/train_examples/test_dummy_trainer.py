import json
import os

from dr_exp.logging.structured_logger import StructuredLogger
from dr_exp.train_examples.dummy_trainer import train


def make_cfg(tmp_path, num_epochs=4):
    return {
        "train": {"num_epochs": num_epochs},
        "logging": {
            "out_path": str(tmp_path / "metrics.jsonl"),
            "checkpoint_dir": str(tmp_path / "checkpoints"),
            "artifact_dir": str(tmp_path / "artifacts"),
        },
    }


def test_train_runs_and_logs(tmp_path):
    cfg = make_cfg(tmp_path, num_epochs=4)
    logger = StructuredLogger(cfg)
    result = train(cfg, logger)

    assert result["status"] == "success"
    assert os.path.exists(cfg["logging"]["out_path"])

    with open(cfg["logging"]["out_path"], "r") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 4
    assert all("epoch" in m for m in lines)

    assert os.path.isdir(cfg["logging"]["checkpoint_dir"])
    checkpoints = list(os.listdir(cfg["logging"]["checkpoint_dir"]))
    assert len(checkpoints) == result["num_checkpoints"]

    artifact_file = os.path.join(cfg["logging"]["artifact_dir"], "loss_plot.txt")
    assert os.path.exists(artifact_file)

    # Ensure result keys are present
    for key in [
        "final_val_acc",
        "final_train_loss",
        "num_epochs",
        "status",
        "metrics_path",
        "artifacts_path",
        "num_checkpoints",
    ]:
        assert key in result


class ObjCfg:
    def __init__(self, tmp_path, num_epochs: int) -> None:
        self.train = {"num_epochs": num_epochs}
        self.logging = {
            "out_path": str(tmp_path / "out.jsonl"),
            "checkpoint_dir": str(tmp_path / "ckpt"),
            "artifact_dir": str(tmp_path / "art"),
        }


def test_train_with_obj_cfg_and_default_logger(tmp_path):
    cfg = ObjCfg(tmp_path, 2)
    result = train(cfg)

    assert result["status"] == "success"
    assert result["num_epochs"] == 2
    assert os.path.exists(cfg.logging["out_path"])
    with open(cfg.logging["out_path"], "r") as f:
        lines = f.readlines()
    assert len(lines) == 2
