from datetime import datetime, UTC, timedelta

from dr_exp.core.localdb_client import LocalDBClient
from dr_exp.utils import reap_stale_jobs


def test_reap_marks_stale_job(tmp_path):
    client = LocalDBClient(base_path=str(tmp_path))
    job = client.add_job({"cfg": 1}, "sweep1", status="running")
    old = datetime.now(UTC) - timedelta(minutes=10)
    client.update_job(job["id"], {"heartbeat": old.isoformat() + "Z"})

    count = reap_stale_jobs(client, max_age_mins=5)
    assert count == 1
    data = client.get_job_details(job["id"])
    assert data["status"] == "failed"
    assert data["status_reason"] == "manager_died"


def test_reap_ignores_recent_job(tmp_path):
    client = LocalDBClient(base_path=str(tmp_path))
    job = client.add_job({"cfg": 1}, "sweep1", status="running")
    now = datetime.now(UTC)
    client.update_job(job["id"], {"heartbeat": now.isoformat() + "Z"})

    count = reap_stale_jobs(client, max_age_mins=5)
    assert count == 0
    data = client.get_job_details(job["id"])
    assert data["status"] == "running"
