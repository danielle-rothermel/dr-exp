import json
from pathlib import Path

from dr_exp.mock.supabase_mock_client import SupabaseMockClient
from scripts import upload_configs


def create_base_config(path: Path) -> None:
    cfg = {"optim": {"lr": 0.1}, "model": {"name": "base"}}
    path.write_text(json.dumps(cfg))


def test_generate_and_upload(tmp_path):
    base = tmp_path / "base.yaml"
    create_base_config(base)
    client = SupabaseMockClient(base_path=str(tmp_path))
    sweep = "optim.lr=0.01,0.02 model.name=a,b"

    jobs = upload_configs.upload_configs(
        base_config=str(base),
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
        assert cfg["model"]["name"] in ["a", "b"]
        assert data["config_id"] == upload_configs.config_hash(cfg)


def test_cli_main(tmp_path, capsys):
    base = tmp_path / "base.yaml"
    create_base_config(base)
    client_path = tmp_path / "env"
    client = SupabaseMockClient(base_path=str(client_path))

    # monkeypatch client inside module
    def mock_client():
        return client

    upload_configs.SupabaseMockClient = mock_client  # type: ignore

    upload_configs.main(
        [
            "--base-config",
            str(base),
            "--sweep",
            "optim.lr=0.1,0.2",
        ]
    )
    out = capsys.readouterr().out
    assert "Created 2 job" in out
