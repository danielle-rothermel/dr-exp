from datetime import datetime, timedelta, UTC
from multiprocessing import Process
from pathlib import Path


from dr_exp.job_db import LocalJobDB, JobDBConfig, JobDBConfig
import dr_exp.manage.manager_logic as manager


def dummy_worker(worker_id: str, work_dir: str) -> None:
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    with open(Path(work_dir) / "started", "w") as f:
        f.write(worker_id)


def test_discover_gpus_env(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,2")
    gpus = manager.discover_gpus(4)
    assert gpus == ["0", "2"]


def test_worker_spawning(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "run_worker_main", dummy_worker)
    client = LocalJobDB(JobDBConfig(base_path=str(tmp_path, storage_path=str(tmp_path + "/storage", mode="mock")), storage_path=str(tmp_path / "storage")
    )
    gpus = ["0", "1"]
    mgr = manager.Manager(
        gpus=gpus,
        workers_per_gpu=2,
        heartbeat_interval=1,
        idle_timeout_mins=1,
        base_dir=str(tmp_path),
        client=client,
    )
    mgr.start_workers()
    for info in mgr.workers.values():
        proc: Process = info["process"]  # type: ignore[assignment]
        proc.join()
    assert len(mgr.workers) == 4
    for wid in mgr.workers:
        started = tmp_path / wid / "started"
        assert started.exists()


def test_heartbeat_detection(tmp_path, monkeypatch):
    client = LocalJobDB(JobDBConfig(base_path=str(tmp_path, storage_path=str(tmp_path + "/storage", mode="mock")), storage_path=str(tmp_path / "storage")
    )
    job = client.add_job({"cfg": 1}, "sweep1", status="running")
    wid = "worker_0_0"
    old_time = datetime.now(UTC) - timedelta(seconds=100)
    client.update_job(
        job["id"],
        {
            "status": "running",
            "assigned_worker": wid,
            "heartbeat": old_time.isoformat() + "Z",
        },
    )
    mgr = manager.Manager(
        gpus=["0"],
        workers_per_gpu=1,
        heartbeat_interval=1,
        idle_timeout_mins=10,
        base_dir=str(tmp_path / "mgr"),
        client=client,
    )
    mgr.workers[wid] = {"process": Process(), "gpu": "0"}
    monkeypatch.setattr(mgr, "_restart_worker", lambda w: mgr.workers.pop(w, None))
    mgr.check_heartbeats()
    data = client.get_job_details(job["id"])
    assert data["status"] == "failed"
    assert data["status_reason"] == "worker_lost"


def test_idle_timeout(tmp_path):
    client = LocalJobDB(JobDBConfig(base_path=str(tmp_path, storage_path=str(tmp_path + "/storage", mode="mock")), storage_path=str(tmp_path / "storage")
    )
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
    assert mgr.shutdown is True


class DummyTable:
    def __init__(self, data):
        self.data = data
        self.filter = None

    def select(self, _fields):
        return self

    def eq(self, field, value):
        self.filter = (field, value)
        return self

    def execute(self):
        if self.filter:
            field, value = self.filter
            filtered = [j for j in self.data if j.get(field) == value]
        else:
            filtered = self.data
        return type("Resp", (), {"data": filtered})()


class DummySupabase:
    def __init__(self, data):
        self._data = data

    def table(self, name):
        assert name == "jobs"
        return DummyTable(self._data)


class DummyRealClient:
    def __init__(self, data, base_path="."):
        self.supabase = DummySupabase(data)
        self.base_path = base_path
        self.jobs_dir = f"{base_path}/job_data"


def test_list_running_jobs_real_client(tmp_path):
    jobs = [
        {"id": "j1", "status": "running"},
        {"id": "j2", "status": "queued"},
    ]
    client = DummyRealClient(jobs, base_path=str(tmp_path))
    mgr = manager.Manager(
        gpus=[],
        workers_per_gpu=0,
        heartbeat_interval=1,
        idle_timeout_mins=1,
        base_dir=str(tmp_path),
        client=client,
    )
    running = mgr._list_running_jobs()
    assert running == [jobs[0]]


def test_restart_worker(monkeypatch, tmp_path):
    class DummyProc:
        def __init__(self):
            self.terminated = False
            self.joined = False

        def is_alive(self):
            return True

        def terminate(self):
            self.terminated = True

        def join(self, timeout=None):
            self.joined = True

    launched = {}

    def fake_launch(self, worker_id, gpu_id):
        launched["worker"] = worker_id

    client = LocalJobDB(JobDBConfig(base_path=str(tmp_path, storage_path=str(tmp_path + "/storage", mode="mock")), storage_path=str(tmp_path / "storage")
    )
    mgr = manager.Manager(
        gpus=["0"],
        workers_per_gpu=1,
        heartbeat_interval=1,
        idle_timeout_mins=1,
        base_dir=str(tmp_path),
        client=client,
    )
    mgr.workers["wid"] = {"process": DummyProc(), "gpu": "0"}
    monkeypatch.setattr(manager.Manager, "launch_worker", fake_launch)

    mgr._restart_worker("wid")

    assert launched.get("worker") == "wid"
