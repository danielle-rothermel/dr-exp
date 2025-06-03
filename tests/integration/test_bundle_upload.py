import zipfile

import dr_exp.worker as run_worker
from dr_exp.mock.supabase_mock_client import SupabaseMockClient


def test_bundle_upload(tmp_path):
    client = SupabaseMockClient(base_path=str(tmp_path))
    job = client.add_job(
        {"train": {"num_epochs": 1}, "logging": {}}, "sweep", status="queued"
    )

    work_dir = tmp_path / "work"
    status = run_worker.run_worker(
        base_path=str(tmp_path),
        work_dir=str(work_dir),
        heartbeat_interval=0.01,
        client=client,
        worker_id="w",
    )
    assert status == "completed"
    storage_run = tmp_path / "mock_storage" / f"run_{job['id']}"
    bundle_zip = storage_run / "bundle.zip"
    assert bundle_zip.exists()
    with zipfile.ZipFile(bundle_zip) as zf:
        names = zf.namelist()
        assert "worker.log" in names
        assert "artifacts/loss_plot.txt" in names
        assert any(n.startswith("checkpoints/") for n in names)
    assert not work_dir.exists()
