import json
from pathlib import Path

from dr_exp.mock.supabase_mock_client import SupabaseMockClient
from dr_exp import config_upload
from scripts import upload_configs


CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"


def test_generate_and_upload(tmp_path):
    cfg_dir = CONFIG_DIR
    client = SupabaseMockClient(base_path=str(tmp_path / "env"))
    sweep = "model=resnet,vit optim.lr=0.01,0.02"

    jobs = config_upload.upload_configs(
        base_config_path=str(cfg_dir),
        config_name="config.yaml",
        sweep=sweep,
        client=client,
        cluster_name="c1",
        description="desc",
        interface_version="v1",
        code_version="123",
    )
    assert len(jobs) == 4
    job_files = list(Path(client.jobs_dir).glob("*.json"))
    assert len(job_files) == 4
    for jf in job_files:
        data = json.loads(jf.read_text())
        cfg = data["config_json"]["config"]
        assert cfg["optim"]["lr"] in [0.01, 0.02]
        assert cfg["model"]["name"] in ["resnet18", "vit_base_patch16_224"]
        assert data["config_id"] == config_upload.config_hash(cfg)


def test_cli_main(tmp_path, capsys):
    cfg_dir = CONFIG_DIR
    client_path = tmp_path / "env"
    client = SupabaseMockClient(base_path=str(client_path))

    # monkeypatch client inside module
    def mock_client():
        return client

    upload_configs.SupabaseMockClient = mock_client  # type: ignore

    upload_configs.main(
        [
            "--base-config-path",
            str(cfg_dir),
            "--config-name",
            "config.yaml",
            "--sweep",
            "model=vit optim.lr=0.1,0.2",
        ]
    )
    out = capsys.readouterr().out
    assert "Created 2 job" in out
