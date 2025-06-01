import argparse
import json
import logging
import os
import signal
import time
from datetime import datetime, timedelta, UTC
from multiprocessing import Process
from typing import Dict, List

from dr_exp.mock.supabase_mock_client import SupabaseMockClient

# Attempt to import the real worker entrypoint if it exists
try:
    from run_worker import main as run_worker_main  # type: ignore
except Exception:  # pragma: no cover - worker script may not exist

    def run_worker_main(*args: object, **kwargs: object) -> None:
        raise RuntimeError("run_worker.py not available")


def discover_gpus(gpus_per_node: int) -> List[str]:
    """Return list of visible GPU IDs as strings."""
    env = os.environ.get("CUDA_VISIBLE_DEVICES")
    if env:
        return [g.strip() for g in env.split(",") if g.strip()]
    return [str(i) for i in range(gpus_per_node)]


class Manager:
    def __init__(
        self,
        gpus: List[str],
        workers_per_gpu: int,
        heartbeat_interval: int,
        idle_timeout_mins: int,
        base_dir: str,
        client: SupabaseMockClient | None = None,
    ) -> None:
        self.gpus = gpus
        self.workers_per_gpu = workers_per_gpu
        self.heartbeat_interval = heartbeat_interval
        self.idle_timeout = timedelta(minutes=idle_timeout_mins)
        self.base_dir = base_dir
        self.client = client or SupabaseMockClient()
        self.workers: Dict[str, Dict[str, object]] = {}
        self.last_activity = datetime.now(UTC)
        self.shutdown = False
        os.makedirs(self.base_dir, exist_ok=True)
        logging.basicConfig(
            filename=os.path.join(self.base_dir, "manager.log"),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )

    # ---------------- Worker Management ------------------
    def _worker_target(self, worker_id: str, gpu_id: str, worker_dir: str) -> None:
        os.environ["CUDA_VISIBLE_DEVICES"] = gpu_id
        os.makedirs(worker_dir, exist_ok=True)
        run_worker_main(worker_id=worker_id, work_dir=worker_dir)  # type: ignore[arg-type]

    def launch_worker(self, worker_id: str, gpu_id: str) -> None:
        """Launch a worker process."""
        worker_dir = os.path.join(self.base_dir, worker_id)
        proc = Process(target=self._worker_target, args=(worker_id, gpu_id, worker_dir))
        proc.start()
        self.workers[worker_id] = {"process": proc, "gpu": gpu_id}
        logging.info("Launched worker %s on GPU %s", worker_id, gpu_id)

    def start_workers(self) -> None:
        for gpu in self.gpus:
            for i in range(self.workers_per_gpu):
                worker_id = f"worker_{gpu}_{i}"
                self.launch_worker(worker_id, gpu)

    def stop_all_workers(self) -> None:
        for info in self.workers.values():
            proc: Process = info["process"]  # type: ignore[assignment]
            if proc.is_alive():
                proc.terminate()
            proc.join(timeout=5)
        self.workers.clear()

    # ---------------- Job & Heartbeat ------------------
    def _list_running_jobs(self) -> List[Dict[str, object]]:
        jobs: List[Dict[str, object]] = []
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
        return jobs

    def _restart_worker(self, worker_id: str) -> None:
        info = self.workers.get(worker_id)
        if not info:
            return
        proc: Process = info["process"]  # type: ignore[assignment]
        gpu = info["gpu"]
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
        self.launch_worker(worker_id, gpu)

    def check_heartbeats(self) -> None:
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
        running = self._list_running_jobs()
        if running:
            self.last_activity = datetime.now(UTC)
            return
        if datetime.now(UTC) - self.last_activity > self.idle_timeout:
            logging.info("Idle timeout reached, shutting down")
            self.shutdown = True

    # ---------------- Main Loop ------------------
    def _handle_signal(
        self, signum: int, frame: object
    ) -> None:  # pragma: no cover - signal path
        logging.info("Received signal %s", signum)
        self.shutdown = True

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        self.start_workers()
        while not self.shutdown:
            self.check_heartbeats()
            self.check_idle_timeout()
            time.sleep(self.heartbeat_interval)
        self.stop_all_workers()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SLURM Manager")
    parser.add_argument("--gpus-per-node", type=int, default=1)
    parser.add_argument("--workers-per-gpu", type=int, default=1)
    parser.add_argument("--heartbeat-interval", type=int, default=10)
    parser.add_argument("--idle-timeout-mins", type=int, default=30)
    return parser


def main(argv: List[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    gpus = discover_gpus(args.gpus_per_node)
    slurm_job_id = os.environ.get("SLURM_JOB_ID", str(os.getpid()))
    base_dir = os.path.join("./manager_runs", f"job_{slurm_job_id}")
    manager = Manager(
        gpus=gpus,
        workers_per_gpu=args.workers_per_gpu,
        heartbeat_interval=args.heartbeat_interval,
        idle_timeout_mins=args.idle_timeout_mins,
        base_dir=base_dir,
    )
    manager.run()


if __name__ == "__main__":  # pragma: no cover - script entry
    main()
