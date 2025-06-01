import os
from multiprocessing import Process

from dr_exp.core import StructuredLogger


class SimpleCfg:
    def __init__(self, out_path: str, artifact_dir: str, checkpoint_dir: str):
        self.logging = type(
            "LogCfg",
            (),
            {
                "out_path": out_path,
                "artifact_dir": artifact_dir,
                "checkpoint_dir": checkpoint_dir,
            },
        )()


def test_logger_basic(tmp_path):
    cfg = SimpleCfg(
        out_path=str(tmp_path / "metrics.jsonl"),
        artifact_dir=str(tmp_path / "artifacts"),
        checkpoint_dir=str(tmp_path / "ckpts"),
    )
    logger = StructuredLogger(cfg)

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

    with open(cfg.logging.out_path) as f:
        lines = f.readlines()
    assert len(lines) == 2
    for line in lines:
        data = line.strip()
        assert data.startswith("{") and data.endswith("}")


def _worker(cfg_dict, count):
    logger = StructuredLogger(cfg_dict)
    for i in range(count):
        logger.log({"i": i})
    logger.finalize()


def test_logger_concurrent(tmp_path):
    cfg_dict = {
        "logging": {
            "out_path": str(tmp_path / "metrics.jsonl"),
            "artifact_dir": str(tmp_path / "artifacts"),
            "checkpoint_dir": str(tmp_path / "ckpts"),
        }
    }

    procs = [Process(target=_worker, args=(cfg_dict, 10)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()

    with open(cfg_dict["logging"]["out_path"], "r") as f:
        lines = f.readlines()
    assert len(lines) == 40
