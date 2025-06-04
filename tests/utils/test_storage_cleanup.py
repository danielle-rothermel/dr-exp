from pathlib import Path

from dr_exp.job_db.local_job_db import LocalDBClient
from dr_exp.utils.storage_cleanup import cleanup_uploaded_runs


def test_cleanup_uploaded_runs(tmp_path):
    client = LocalDBClient(
        base_path=str(tmp_path), storage_path=str(tmp_path / "storage")
    )
    run1 = Path(client.storage_dir) / "run_a"
    run1.mkdir(parents=True)
    (run1 / "finished.flag").write_text("done")
    run2 = Path(client.storage_dir) / "run_b"
    run2.mkdir(parents=True)

    count = cleanup_uploaded_runs(client)
    assert count == 1
    assert not run1.exists()
    assert run2.exists()
