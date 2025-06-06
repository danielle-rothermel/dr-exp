import json
from pathlib import Path

import pytest

from dr_exp.utils import config_upload
from dr_exp.api.main import MetricsLoader
from dr_exp.utils import jobdb_factory as client_provider
from dr_exp.job_db import LocalJobDB, JobDBConfig


def test_parse_sweep_and_generate_combos():
    params = config_upload.parse_sweep("lr=0.1,0.2 model=resnet,vit")
    assert params == {"lr": ["0.1", "0.2"], "model": ["resnet", "vit"]}
    combos = list(config_upload._generate_override_combinations(params))
    assert combos == [
        ["lr=0.1", "model=resnet"],
        ["lr=0.1", "model=vit"],
        ["lr=0.2", "model=resnet"],
        ["lr=0.2", "model=vit"],
    ]


def test_parse_sweep_with_spaces():
    params = config_upload.parse_sweep("lr=0.1, 0.2 model = resnet, vit")
    assert params == {
        "lr": ["0.1", "0.2"],
        "model": ["resnet", "vit"],
    }


def test_generate_configs(tmp_path):
    cfg_dir = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dr_exp"
        / "train_examples"
        / "configs"
    )
    params = {"model": ["resnet", "vit"]}
    configs = list(config_upload.generate_configs(str(cfg_dir), "config.yaml", params))
    names = {cfg["model"]["name"] for cfg in configs}
    assert names == {"resnet18", "vit_base_patch16_224"}


def test_config_hash_deterministic():
    cfg = {"a": 1, "b": [2, 3]}
    h1 = config_upload.config_hash(cfg)
    h2 = config_upload.config_hash({"b": [2, 3], "a": 1})
    assert h1 == h2


def test_get_supabase_client_modes(monkeypatch, tmp_path):
    monkeypatch.delenv("EXPMGR_MODE", raising=False)
    client = client_provider.get_job_db_client()
    assert isinstance(client, LocalJobDB)

    class Dummy:
        def __init__(self, config):
            self.config = config
            self.url = config.supabase_url
            self.key = config.supabase_key
            self.base_path = config.base_path

    monkeypatch.setenv("EXPMGR_MODE", "supabase_remote")
    monkeypatch.setenv("SUPABASE_URL", "http://x")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    monkeypatch.setattr("dr_exp.utils.jobdb_factory.SupabaseJobDB", Dummy)
    client = client_provider.get_job_db_client()
    assert isinstance(client, Dummy)
    assert client.url == "http://x"
    assert client.key == "k"

    monkeypatch.setenv("EXPMGR_MODE", "supabase_remote")
    monkeypatch.delenv("SUPABASE_URL")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY")
    with pytest.raises(ValueError):
        client_provider.get_job_db_client()


def test_metrics_loader(tmp_path):
    config = JobDBConfig(base_path=str(tmp_path), storage_path=str(tmp_path / "storage"), mode="files_local")
    client = LocalJobDB(config)
    loader = MetricsLoader(client, maxsize=2)
    run_id = "r1"
    run_dir = Path(client.storage_dir) / f"run_{run_id}"
    run_dir.mkdir(parents=True)
    metrics_file = run_dir / "metrics.jsonl"
    with open(metrics_file, "w") as f:
        for i in range(150):
            f.write(json.dumps({"step": i}) + "\n")
    data = loader.load(run_id)
    assert len(data) == 100
    assert data[-1]["step"] == 149
    # cached result should not change if file updated
    with open(metrics_file, "a") as f:
        f.write(json.dumps({"step": 999}) + "\n")
    cached = loader.load(run_id)
    assert cached == data
    with pytest.raises(FileNotFoundError):
        loader.load("missing")

    class Real:
        pass

    with pytest.raises(NotImplementedError):
        MetricsLoader(Real()).load("x")
