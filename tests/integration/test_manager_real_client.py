from datetime import datetime, UTC, timedelta

import dr_exp.manager as manager


class DummyTable:
    def __init__(self, data):
        self.data = data

    def select(self, _):
        return self

    def eq(self, field, value):
        return self

    def execute(self):
        return type("Resp", (), {"data": self.data})()


class DummySupabase:
    def __init__(self, data):
        self._data = data

    def table(self, name):
        return DummyTable(self._data)


class DummyClient:
    def __init__(self, jobs):
        self.supabase = DummySupabase(jobs)
        self.updated = []

    def update_job(self, job_id, data):
        self.updated.append((job_id, data))


def test_idle_timeout_real_client(tmp_path):
    jobs = [
        {
            "id": "j1",
            "status": "running",
            "heartbeat": datetime.now(UTC).isoformat() + "Z",
        }
    ]
    client = DummyClient(jobs)
    mgr = manager.Manager(
        gpus=[],
        workers_per_gpu=0,
        heartbeat_interval=1,
        idle_timeout_mins=0,
        base_dir=str(tmp_path),
        client=client,
    )
    mgr.last_activity = datetime.now(UTC) - timedelta(minutes=1)
    mgr.check_idle_timeout()
    assert not mgr.shutdown
