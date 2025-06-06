"""Manager module for orchestrating training workers."""

import json
import logging
import os
import signal
import time
from datetime import datetime, timedelta, UTC
import multiprocessing as mp
from dotenv import load_dotenv
from typing import Dict, List

from dr_exp.utils.jobdb_factory import get_supabase_client
from dr_exp.job_db.base_job_db import BaseJobDB

# Import the worker implementation from this package
from . import worker_logic as _run_worker

load_dotenv()


def run_worker_main(worker_id: str, work_dir: str) -> None:
    """Wrapper to execute the worker with base path from env."""
    base_path = os.environ.get("DR_EXP_BASE_PATH", "./job_data")
    _run_worker.run_worker(base_path=base_path, work_dir=work_dir, worker_id=worker_id)


def _worker_target(
    base_path: str, worker_id: str, gpu_id: str, worker_dir: str
) -> None:
    """Entry point for spawned worker processes."""
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu_id
    os.environ["DR_EXP_BASE_PATH"] = base_path
    os.makedirs(worker_dir, exist_ok=True)
    run_worker_main(worker_id=worker_id, work_dir=worker_dir)  # type: ignore[arg-type]


def discover_gpus(gpus_per_node: int) -> List[str]:
    """Return list of visible GPU IDs as strings."""
    env = os.environ.get("CUDA_VISIBLE_DEVICES")
    if env:
        return [g.strip() for g in env.split(",") if g.strip()]
    return [str(i) for i in range(gpus_per_node)]


class Manager:
    """Manage worker processes running training jobs."""

    def __init__(
        self,
        gpus: List[str],
        workers_per_gpu: int,
        heartbeat_interval: int,
        idle_timeout_mins: int,
        base_dir: str,
        client: BaseJobDB | None = None,
        start_method: str | None = "fork",
    ) -> None:
        """Create a new :class:`Manager`."""
        self.gpus = gpus
        self.workers_per_gpu = workers_per_gpu
        self.heartbeat_interval = heartbeat_interval
        self.idle_timeout = timedelta(minutes=idle_timeout_mins)
        self.base_dir = base_dir
        self.client = client or get_supabase_client()
        # Extract base_path from client's jobs_dir (remove "/job_data" suffix)
        if self.client.jobs_dir.endswith("/job_data"):
            self.base_path = self.client.jobs_dir[:-9]  # Remove "/job_data"
        else:
            self.base_path = os.path.dirname(self.client.jobs_dir)
        self.workers: Dict[str, Dict[str, object]] = {}
        self.last_activity = datetime.now(UTC)
        self.shutdown = False
        try:
            self.ctx = (
                mp.get_context(start_method) if start_method else mp.get_context()
            )
        except ValueError:
            self.ctx = mp.get_context()
        os.makedirs(self.base_dir, exist_ok=True)
        logging.basicConfig(
            filename=os.path.join(self.base_dir, "manager.log"),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            force=True,
        )

    # ---------------- Worker Management ------------------

    def launch_worker(self, worker_id: str, gpu_id: str) -> None:
        """Launch a worker process."""
        worker_dir = os.path.join(self.base_dir, worker_id)
        proc = self.ctx.Process(
            target=_worker_target,
            args=(self.base_path, worker_id, gpu_id, worker_dir),
        )
        proc.start()
        self.workers[worker_id] = {"process": proc, "gpu": gpu_id}
        logging.info("Launched worker %s on GPU %s", worker_id, gpu_id)

    def start_workers(self) -> None:
        """Spawn all configured worker processes."""
        for gpu in self.gpus:
            for i in range(self.workers_per_gpu):
                worker_id = f"worker_{gpu}_{i}"
                self.launch_worker(worker_id, gpu)

    def stop_all_workers(self) -> None:
        """Terminate all running worker processes."""
        for info in self.workers.values():
            proc: mp.Process = info["process"]  # type: ignore[assignment]
            if proc.is_alive():
                proc.terminate()
            proc.join(timeout=5)
        self.workers.clear()

    # ---------------- Job & Heartbeat ------------------
    def list_jobs_by_priority(self, status_filter: List[str] = None, limit: int = 10) -> List[Dict[str, object]]:
        """List jobs ordered by priority for monitoring purposes."""
        try:
            return self.client.list_jobs_by_priority(status_filter=status_filter, limit=limit)
        except AttributeError:
            # Fallback for clients without priority support
            logging.warning("Client does not support priority listing")
            return []

    def _list_running_jobs(self) -> List[Dict[str, object]]:
        """Return job records currently marked as running."""
        jobs: List[Dict[str, object]] = []
        if hasattr(self.client, "jobs_dir") and not hasattr(self.client, "supabase"):
            for name in os.listdir(self.client.jobs_dir):
                if not name.endswith(".json"):
                    continue
                path = os.path.join(self.client.jobs_dir, name)
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                    if data.get("status") == "running":
                        jobs.append(data)
                except Exception as e:  # pragma: no cover - corrupted job file
                    logging.error("Failed to read job file %s: %s", path, e)
        else:  # real client path
            try:
                resp = (
                    self.client.supabase.table("jobs")
                    .select("*")
                    .eq("status", "running")
                    .execute()
                )
                jobs = resp.data or []
            except Exception as e:  # pragma: no cover - unexpected client error
                logging.error("Failed to query running jobs: %s", e)
                jobs = []
        return jobs

    def _restart_worker(self, worker_id: str) -> None:
        """Restart the given worker process."""
        info = self.workers.get(worker_id)
        if not info:
            return
        proc: mp.Process = info["process"]  # type: ignore[assignment]
        gpu = info["gpu"]
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
        self.launch_worker(worker_id, gpu)

    def check_heartbeats(self) -> None:
        """Check for stale worker heartbeats and restart if necessary."""
        now = datetime.now(UTC)
        for job in self._list_running_jobs():
            hb_str = job.get("heartbeat")
            wid = job.get("assigned_worker")
            if not hb_str or not wid:
                continue
            try:
                hb_time = datetime.fromisoformat(hb_str.replace("Z", ""))
            except ValueError:
                continue
            if now - hb_time > timedelta(seconds=self.heartbeat_interval * 2):
                logging.warning("Stale heartbeat for job %s", job.get("id"))
                self.client.update_job(
                    job["id"],
                    {"status": "failed", "status_reason": "worker_lost"},
                )
                self._restart_worker(str(wid))

    def check_idle_timeout(self) -> None:
        """Shutdown manager if idle for longer than ``idle_timeout``."""
        running = self._list_running_jobs()
        if running:
            self.last_activity = datetime.now(UTC)
            return
        
        # Log queue status before potential shutdown
        queued_jobs = self.list_jobs_by_priority(status_filter=["queued"], limit=5)
        if queued_jobs:
            logging.info("Queued jobs (top 5 by priority): %s", 
                        [{"id": j.get("id"), "priority": j.get("priority", 100)} for j in queued_jobs])
        
        if datetime.now(UTC) - self.last_activity > self.idle_timeout:
            logging.info("Idle timeout reached, shutting down")
            self.shutdown = True

    # ---------------- Main Loop ------------------
    def _handle_signal(
        self, signum: int, frame: object
    ) -> None:  # pragma: no cover - signal path
        """Handle termination signals to initiate shutdown."""
        logging.info("Received signal %s", signum)
        self.shutdown = True

    def run(self) -> None:
        """Run the manager main loop."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        self.start_workers()
        while not self.shutdown:
            self.check_heartbeats()
            self.check_idle_timeout()
            time.sleep(self.heartbeat_interval)
        self.stop_all_workers()


__all__ = ["Manager", "discover_gpus", "run_worker_main"]
