import json
from pathlib import Path
from typing import Any, Dict

import pytest

from dr_exp.utils import config_upload
from dr_exp.api.main import MetricsLoader
from dr_exp.utils import jobdb_factory as client_provider
from dr_exp.job_db import LocalJobDB, JobDBConfig


def test_parse_sweep_and_generate_combos() -> None:
    params = config_upload.parse_sweep("lr=0.1,0.2 model=resnet,vit")
    assert params == {"lr": ["0.1", "0.2"], "model": ["resnet", "vit"]}
    combos = list(config_upload._generate_override_combinations(params))
    assert combos == [
        ["lr=0.1", "model=resnet"],
        ["lr=0.1", "model=vit"],
        ["lr=0.2", "model=resnet"],
        ["lr=0.2", "model=vit"],
    ]


def test_parse_sweep_with_spaces() -> None:
    params = config_upload.parse_sweep("lr=0.1, 0.2 model = resnet, vit")
    assert params == {
        "lr": ["0.1", "0.2"],
        "model": ["resnet", "vit"],
    }


def test_generate_configs(tmp_path: Path) -> None:
    cfg_dir = Path(__file__).resolve().parents[2] / "configs"
    params = {"model": ["resnet18_cifar", "alexnet_cifar"]}
    configs = list(
        config_upload.generate_configs(str(cfg_dir), "decon_config.yaml", params)
    )

    # Check what keys exist in model config
    assert len(configs) == 2

    # For resnet18_cifar, check for architecture
    resnet_config = next(cfg["model"] for cfg in configs if "resnet18" in str(cfg))
    assert resnet_config["architecture"] == "resnet18"

    # For alexnet_cifar, check for architecture
    alexnet_config = next(cfg["model"] for cfg in configs if "alexnet" in str(cfg))
    assert alexnet_config["architecture"] == "CifarAlexNet"


def test_config_hash_deterministic() -> None:
    cfg: Dict[str, Any] = {"a": 1, "b": [2, 3]}
    h1 = config_upload.config_hash(cfg)
    h2 = config_upload.config_hash({"b": [2, 3], "a": 1})
    assert h1 == h2


def test_get_supabase_client_modes(monkeypatch: Any, tmp_path: Path) -> None:
    # Test files_local mode
    config_local = JobDBConfig(
        base_path=str(tmp_path),
        mode="files_local",
        storage_path=str(tmp_path / "storage"),
    )
    config_local.validate()
    client = client_provider.get_job_db_client(config_local)
    assert isinstance(client, LocalJobDB)

    class Dummy:
        def __init__(self, config: Any) -> None:
            self.config = config
            self.url = config.supabase_url
            self.key = config.supabase_key
            self.base_path = config.base_path

    # Test supabase_remote mode with credentials
    monkeypatch.setenv("SUPABASE_URL", "http://x")
    monkeypatch.setenv("SUPABASE_KEY", "k")
    monkeypatch.setattr("dr_exp.utils.jobdb_factory.SupabaseJobDB", Dummy)

    config_remote = JobDBConfig(
        base_path=str(tmp_path),
        mode="supabase_remote",
        storage_path=str(tmp_path / "storage"),
    )
    config_remote.validate()
    client = client_provider.get_job_db_client(config_remote)
    assert isinstance(client, Dummy)
    assert client.url == "http://x"
    assert client.key == "k"

    # Test supabase_remote mode without credentials (should fail)
    monkeypatch.delenv("SUPABASE_URL")
    monkeypatch.delenv("SUPABASE_KEY")

    # JobDBConfig now validates automatically in __post_init__, so we expect ValueError at construction
    with pytest.raises(ValueError):
        JobDBConfig(
            base_path=str(tmp_path),
            mode="supabase_remote",
            storage_path=str(tmp_path / "storage"),
        )


def test_metrics_loader(tmp_path: Path) -> None:
    config = JobDBConfig(
        base_path=str(tmp_path),
        storage_path=str(tmp_path / "storage"),
        mode="files_local",
    )
    client = LocalJobDB(config)
    loader = MetricsLoader(client, maxsize=2)
    run_id = "r1"
    run_dir = Path(client.storage_dir) / f"run_{run_id}"
    run_dir.mkdir(parents=True)
    metrics_file = run_dir / "metrics.jsonl"
    with open(metrics_file, "w") as f:
        for i in range(150):
            f.write(json.dumps({"step": i}) + "\n")
    data = loader.load(run_id, limit=100)
    assert len(data) == 100
    assert data[-1]["step"] == 149
    # cached result should not change if file updated
    with open(metrics_file, "a") as f:
        f.write(json.dumps({"step": 999}) + "\n")
    cached = loader.load(run_id, limit=100)
    assert cached == data
    with pytest.raises(FileNotFoundError):
        loader.load("missing")

    class Real:
        def get_metrics(self, run_id: str, limit: int | None = None) -> Any:
            raise NotImplementedError()

    with pytest.raises(NotImplementedError):
        MetricsLoader(Real()).load("x")  # type: ignore[arg-type]
