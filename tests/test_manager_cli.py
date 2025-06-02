from __future__ import annotations

import os
from pathlib import Path

from dr_exp.manager_cli import main
from dr_exp.mock.supabase_mock_client import SupabaseMockClient


def make_config() -> dict:
    return {"train": {"num_epochs": 1}, "logging": {}}


def test_discover_gpus(monkeypatch, capsys):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,2")
    main(["discover-gpus"])
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["0", "2"]


def test_run_worker_subcommand(tmp_path, monkeypatch):
    client = SupabaseMockClient(base_path=str(tmp_path))
    client.add_job(make_config(), "s1", status="queued")
    monkeypatch.setenv("DR_EXP_BASE_PATH", str(tmp_path))
    work_dir = tmp_path / "work"
    main(["run-worker", "wid", str(work_dir)])
    job_files = os.listdir(client.jobs_dir)
    job_id = Path(job_files[0]).stem
    data = client.get_job_details(job_id)
    assert data["status"] == "completed"


def test_run_subcommand_invokes_manager(monkeypatch):
    called = {}

    def fake_run(self):
        called["run"] = True

    monkeypatch.setattr("dr_exp.manager.Manager.run", fake_run)
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


def test_upload_configs_subcommand(tmp_path, monkeypatch, capsys):
    cfg_dir = Path(__file__).resolve().parents[1] / "configs"
    client = SupabaseMockClient(base_path=str(tmp_path))

    monkeypatch.setattr("scripts.upload_configs.SupabaseMockClient", lambda: client)

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
