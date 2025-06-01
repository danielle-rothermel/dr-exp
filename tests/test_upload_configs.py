import json
from pathlib import Path

from dr_exp.mock.supabase_mock_client import SupabaseMockClient
from scripts import upload_configs


def create_hydra_config(base_dir: Path) -> Path:
    """Create a minimal Hydra config directory structure."""
    cfg_dir = base_dir / "cfg"
    (cfg_dir / "model").mkdir(parents=True)
    (cfg_dir / "optimizer").mkdir()

    (cfg_dir / "model" / "resnet.yaml").write_text("name: resnet18\n")
    (cfg_dir / "model" / "vit.yaml").write_text("name: vit\n")
    (cfg_dir / "optimizer" / "adam.yaml").write_text("lr: 0.001\n")

    (cfg_dir / "config.yaml").write_text(
        "\n".join(
            [
                "defaults:",
                "  - model: resnet",
                "  - optimizer: adam",
                "  - override hydra/launcher: basic",
            ]
        )
    )
    return cfg_dir


def test_generate_and_upload(tmp_path):
    cfg_dir = create_hydra_config(tmp_path)
    client = SupabaseMockClient(base_path=str(tmp_path / "env"))
    sweep = "model=resnet,vit optimizer.lr=0.01,0.02"

    jobs = upload_configs.upload_configs(
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
        assert cfg["optimizer"]["lr"] in [0.01, 0.02]
        assert cfg["model"]["name"] in ["resnet18", "vit"]
        assert data["config_id"] == upload_configs.config_hash(cfg)


def test_cli_main(tmp_path, capsys):
    cfg_dir = create_hydra_config(tmp_path)
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
            "model=vit optimizer.lr=0.1,0.2",
        ]
    )
    out = capsys.readouterr().out
    assert "Created 2 job" in out
