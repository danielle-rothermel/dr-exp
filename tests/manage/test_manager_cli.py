from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, UTC, timedelta

from scripts.manager_cli import main
from dr_exp.job_db.local_job_db import LocalDBClient


def make_config() -> dict:
    return {"train": {"num_epochs": 1}, "logging": {}}


def test_discover_gpus(monkeypatch, capsys):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,2")
    main(["discover-gpus"])
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["0", "2"]


def test_run_worker_subcommand(tmp_path, monkeypatch):
    client = LocalDBClient(
        base_path=str(tmp_path), storage_path=str(tmp_path / "storage")
    )
    client.add_job(make_config(), "s1", status="queued")
    monkeypatch.setenv("DR_EXP_BASE_PATH", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    work_dir = tmp_path / "work"
    main(["run-worker", "wid", str(work_dir)])
    job_files = [f for f in os.listdir(client.jobs_dir) if f.endswith(".json")]
    job_id = Path(job_files[0]).stem
    data = client.get_job_details(job_id)
    assert data["status"] == "completed"


def test_run_subcommand_invokes_manager(tmp_path, monkeypatch):
    called = {}

    def fake_run(self):
        called["run"] = True

    monkeypatch.setattr("dr_exp.manage.manager_logic.Manager.run", fake_run)
    client = LocalDBClient(
        base_path=str(tmp_path), storage_path=str(tmp_path / "storage")
    )

    def fake_get_client(base_path="."):
        assert base_path == str(tmp_path)
        return client

    monkeypatch.setattr("scripts.manager_cli.get_supabase_client", fake_get_client)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DR_EXP_BASE_PATH", str(tmp_path))
    main(
        [
            "run",
            "--gpus-per-node",
            "1",
            "--workers-per-gpu",
            "1",
            "--heartbeat-interval",
            "1",
            "--idle-timeout-mins",
            "1",
        ]
    )
    assert called.get("run")


def test_reap_stale_jobs_subcommand(tmp_path, monkeypatch, capsys):
    client = LocalDBClient(
        base_path=str(tmp_path), storage_path=str(tmp_path / "storage")
    )
    job = client.add_job(make_config(), "s1", status="running")
    old = datetime.now(UTC) - timedelta(minutes=10)
    client.update_job(job["id"], {"heartbeat": old.isoformat() + "Z"})
    capsys.readouterr()  # flush add_job output

    def fake_get_supabase_client(base_path="."):
        assert base_path == str(tmp_path)
        return client

    monkeypatch.setattr(
        "scripts.manager_cli.get_supabase_client", fake_get_supabase_client
    )
    main(["reap-stale-jobs", "--max-age-mins", "5", "--base-path", str(tmp_path)])
    out = capsys.readouterr().out.strip()
    assert out == "Marked 1 stale job(s) as failed"
    data = client.get_job_details(job["id"])
    assert data["status"] == "failed"
    assert data["status_reason"] == "manager_died"


def test_upload_configs_subcommand(tmp_path, monkeypatch, capsys):
    cfg_dir = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dr_exp"
        / "train_examples"
        / "configs"
    )
    client = LocalDBClient(
        base_path=str(tmp_path), storage_path=str(tmp_path / "storage")
    )

    monkeypatch.setattr("scripts.upload_configs.LocalDBClient", lambda: client)

    main(
        [
            "upload-configs",
            "--base-config-path",
            str(cfg_dir),
            "--config-name",
            "config.yaml",
            "--sweep",
            "model=vit",
        ]
    )
    out = capsys.readouterr().out
    assert "Created 1 job" in out


def test_cleanup_run_data_subcommand(tmp_path, monkeypatch, capsys):
    client = LocalDBClient(
        base_path=str(tmp_path), storage_path=str(tmp_path / "storage")
    )
    run_dir = Path(client.jobs_dir) / "run_x"
    run_dir.mkdir(parents=True)
    (run_dir / "finished.flag").touch()

    def fake_get_supabase_client(base_path="."):
        assert base_path == str(tmp_path)
        return client

    monkeypatch.setattr(
        "scripts.manager_cli.get_supabase_client", fake_get_supabase_client
    )
    main(["cleanup-run-data", "--base-path", str(tmp_path)])
    out = capsys.readouterr().out.strip()
    assert out == "Removed 1 run directory(s)"
    assert not run_dir.exists()
