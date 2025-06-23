"""Multi-worker launcher for GPU clusters."""

import os
import signal
import subprocess
import sys
import time
import json
from pathlib import Path
from datetime import datetime, UTC
from typing import TYPE_CHECKING
import logging
import contextlib

if TYPE_CHECKING:
    from dr_exp.core.job_db import JobDB

# Configure logging for launcher
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)  # Console output
    ],
)

logger = logging.getLogger(__name__)

# Constants
STATUS_WRITE_INTERVAL = 60  # Write status every minute
MAINTENANCE_INTERVAL = 600  # Run maintenance every 10 minutes
WORKER_CHECK_INTERVAL = 5  # Check worker health every 5 seconds
GRACEFUL_SHUTDOWN_TIMEOUT = 5  # Wait 5 seconds before force kill


class WorkerLauncher:
    """Launches and monitors multiple workers across GPUs."""

    def __init__(
        self,
        job_db: "JobDB",
        experiment_name: str,
        base_log_dir: Path,
        workers_per_gpu: int = 2,
        restart_on_failure: bool = True,
        max_runtime_hours: float = 47,  # Leave buffer before 48h SLURM limit
    ) -> None:
        """Initialize launcher.

        Args:
            job_db: JobDB instance
            experiment_name: Name of experiment
            base_log_dir: Base directory for logs
            workers_per_gpu: Number of workers per GPU
            restart_on_failure: Whether to restart failed workers
            max_runtime_hours: Maximum runtime before graceful shutdown
        """
        self.job_db = job_db
        self.experiment_name = experiment_name
        self.workers_per_gpu = workers_per_gpu
        self.restart_on_failure = restart_on_failure
        self.max_runtime_seconds = max_runtime_hours * 3600

        # SLURM info
        self.slurm_job_id = os.environ.get("SLURM_JOB_ID", "local")
        self.slurm_node_name = os.environ.get("SLURMD_NODENAME", "local")

        # Create log directory
        self.log_dir = base_log_dir / f"slurm_{self.slurm_job_id}"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Set up file logging for this launcher instance
        launcher_log_file = self.log_dir / f"launcher_{self.slurm_job_id}.log"
        file_handler = logging.FileHandler(launcher_log_file)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)

        # Control files
        self.control_dir = self.job_db.control_dir
        self.stop_file = self.control_dir / f"stop_{self.slurm_job_id}"
        self.finish_current_file = (
            self.control_dir / f"finish_current_{self.slurm_job_id}"
        )

        # Process tracking
        self.processes: dict[str, subprocess.Popen[bytes]] = {}
        self.worker_restarts: dict[str, int] = {}
        self.start_time = time.time()
        self.running = False

        # Signal handling
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def discover_gpus(self) -> list[int]:
        """Discover available GPUs.

        Returns:
            List of GPU indices
        """
        # First check CUDA_VISIBLE_DEVICES
        cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
        if cuda_visible:
            try:
                return [int(gpu) for gpu in cuda_visible.split(",") if gpu.strip()]
            except ValueError:
                logger.warning(f"Invalid CUDA_VISIBLE_DEVICES: {cuda_visible}")

        # Fall back to nvidia-smi
        # Note: subprocess call is safe - using hardcoded trusted nvidia-smi command
        try:
            result = subprocess.run(  # noqa: S603 - trusted nvidia-smi command
                ["/usr/bin/nvidia-smi", "--list-gpus"],  # Use full path for security
                capture_output=True,
                text=True,
                check=True,
            )
            gpu_count = len(result.stdout.strip().split("\n"))
            return list(range(gpu_count))
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("No GPUs detected, running in CPU mode")
            return []

    def spawn_worker(self, gpu_index: int | None, worker_index: int) -> str:
        """Spawn a single worker process.

        Args:
            gpu_index: GPU to assign (None for CPU)
            worker_index: Worker index on this GPU

        Returns:
            Worker ID
        """
        # Create unique worker ID
        if gpu_index is not None:
            worker_id = (
                f"slurm{self.slurm_job_id}_{self.slurm_node_name}_gpu{gpu_index}_{worker_index}"
            )
        else:
            worker_id = (
                f"slurm{self.slurm_job_id}_{self.slurm_node_name}_cpu_{worker_index}"
            )

        # Set up environment
        env = os.environ.copy()
        if gpu_index is not None:
            env["CUDA_VISIBLE_DEVICES"] = str(gpu_index)

        # Worker log file
        worker_log = self.log_dir / f"{worker_id}.log"

        # Launch worker process
        cmd = [
            sys.executable,
            "-m",
            "dr_exp.cli.main",
            "--base-path",
            str(self.job_db.base_path),
            "--experiment",
            self.experiment_name,
            "worker",
            "--worker-id",
            worker_id,
            "--working-dir",
            str(self.log_dir / worker_id),
        ]

        logger.info(f"Spawning worker {worker_id} on GPU {gpu_index}")

        with worker_log.open("w") as log_file:
            # Note: subprocess call is safe - using trusted dr_exp CLI command
            # preexec_fn usage: Required for proper process group management in HPC
            process = subprocess.Popen(  # noqa: S603 - trusted dr_exp CLI command
                cmd,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,  # noqa: PLW1509 - required for process groups
            )

        self.processes[worker_id] = process
        self.worker_restarts[worker_id] = self.worker_restarts.get(worker_id, 0) + 1

        return worker_id

    def check_worker_health(self) -> dict[str, str]:
        """Check health of all workers.

        Returns:
            Dict of worker_id -> status
        """
        status = {}

        for worker_id, process in list(self.processes.items()):
            poll = process.poll()
            if poll is None:
                status[worker_id] = "running"
            else:
                status[worker_id] = f"exited({poll})"
                # Remove from tracking
                del self.processes[worker_id]

                # Check if we should restart
                if self.restart_on_failure and self.running and self.has_pending_jobs():
                    # Extract GPU info from worker ID
                    if "_gpu" in worker_id:
                        parts = worker_id.split("_gpu")
                        gpu_part = parts[1].split("_")[0]
                        gpu_index = int(gpu_part)
                        worker_index = int(parts[1].split("_")[1])
                        self.spawn_worker(gpu_index, worker_index)
                    elif "_cpu" in worker_id:
                        worker_index = int(worker_id.split("_cpu_")[1])
                        self.spawn_worker(None, worker_index)

        return status

    def has_pending_jobs(self) -> bool:
        """Check if there are queued jobs."""
        queued = self.job_db.list_jobs(status="queued")
        return len(queued) > 0

    def check_control_files(self) -> str | None:
        """Check for control file commands.

        Returns:
            Command if found, None otherwise
        """
        if self.stop_file.exists():
            logger.info("Stop file detected")
            self.stop_file.unlink()
            return "stop"

        if self.finish_current_file.exists():
            logger.info("Finish-current file detected")
            self.finish_current_file.unlink()
            return "finish_current"

        return None

    def write_status(self) -> None:
        """Write launcher status to file."""
        worker_status = self.check_worker_health()

        status_data = {
            "launcher": {
                "slurm_job_id": self.slurm_job_id,
                "node": self.slurm_node_name,
                "start_time": datetime.fromtimestamp(self.start_time, UTC).isoformat(),
                "runtime_seconds": int(time.time() - self.start_time),
                "running": self.running,
            },
            "workers": worker_status,
            "restarts": self.worker_restarts,
            "jobs": {
                "queued": len(self.job_db.list_jobs(status="queued")),
                "running": len(self.job_db.list_jobs(status="running")),
                "completed": len(self.job_db.list_jobs(status="completed")),
                "failed": len(self.job_db.list_jobs(status="failed")),
            },
        }

        status_file = self.control_dir / f"status_{self.slurm_job_id}.json"
        with status_file.open("w") as f:
            json.dump(status_data, f, indent=2)

    def aggregate_errors(self) -> None:
        """Aggregate errors from worker logs."""
        error_file = self.log_dir / "errors.log"

        with error_file.open("w") as err_out:
            err_out.write(f"Error aggregation at {datetime.now(UTC).isoformat()}\n")
            err_out.write("=" * 80 + "\n\n")

            for log_file in self.log_dir.glob("*.log"):
                if log_file.name == "errors.log":
                    continue

                # Look for errors in log
                errors_found = False
                with log_file.open() as f:
                    for line in f:
                        if any(
                            marker in line.lower()
                            for marker in ["error", "exception", "traceback"]
                        ):
                            if not errors_found:
                                err_out.write(f"\n### Errors from {log_file.name}\n")
                                errors_found = True
                            err_out.write(line)

    def run(self) -> None:
        """Run the launcher main loop."""
        self.running = True
        logger.info(f"Starting launcher on node {self.slurm_node_name}")

        # Discover GPUs
        gpus = self.discover_gpus()
        logger.info(f"Found {len(gpus)} GPUs: {gpus}")

        # Spawn initial workers
        if gpus:
            for gpu_index in gpus:
                for worker_index in range(self.workers_per_gpu):
                    self.spawn_worker(gpu_index, worker_index)
        else:
            # CPU only mode
            for worker_index in range(self.workers_per_gpu):
                self.spawn_worker(None, worker_index)

        # Main monitoring loop
        last_status_write = 0.0
        last_maintenance = 0.0

        while self.running:
            try:
                # Check runtime limit
                if time.time() - self.start_time > self.max_runtime_seconds:
                    logger.info("Reached maximum runtime, initiating graceful shutdown")
                    self.stop()
                    break

                # Check control files
                command = self.check_control_files()
                if command == "stop":
                    self.stop()
                    break
                elif command == "finish_current":
                    self.finish_current()
                    break

                # Write status every minute
                if time.time() - last_status_write > STATUS_WRITE_INTERVAL:
                    self.write_status()
                    last_status_write = time.time()

                # Run maintenance every 10 minutes
                if time.time() - last_maintenance > MAINTENANCE_INTERVAL:
                    self.maintenance()
                    last_maintenance = time.time()

                # Check worker health
                self.check_worker_health()

                # Sleep briefly
                time.sleep(WORKER_CHECK_INTERVAL)

            except KeyboardInterrupt:
                logger.info("Received interrupt, shutting down")
                self.stop()
                break

        # Final cleanup
        self.cleanup()

    def maintenance(self) -> None:
        """Run periodic maintenance tasks."""
        logger.info("Running maintenance")

        # Recover stale jobs
        recovered = self.job_db.recover_stale_jobs()
        if recovered:
            logger.info(f"Recovered {len(recovered)} stale jobs")

        # Aggregate errors
        self.aggregate_errors()

        # Log summary
        logger.info(f"Workers alive: {len(self.processes)}")
        logger.info(f"Jobs queued: {len(self.job_db.list_jobs(status='queued'))}")
        logger.info(f"Runtime: {(time.time() - self.start_time) / 3600:.1f} hours")

    def stop(self) -> None:
        """Stop all workers immediately."""
        self.running = False
        logger.info("Stopping all workers")

        # Send SIGTERM to all workers
        for worker_id, process in self.processes.items():
            logger.info(f"Terminating {worker_id}")
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)

        # Wait briefly for graceful shutdown
        time.sleep(GRACEFUL_SHUTDOWN_TIMEOUT)

        # Force kill any remaining
        for worker_id, process in list(self.processes.items()):
            if process.poll() is None:
                logger.warning(f"Force killing {worker_id}")
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)

    def finish_current(self) -> None:
        """Let workers finish current jobs then stop."""
        self.running = False
        logger.info("Finishing current jobs then stopping")

        # Don't spawn new workers
        self.restart_on_failure = False

        # Wait for all workers to finish
        while self.processes:
            self.check_worker_health()

            # Check if any are still working
            running_jobs = self.job_db.list_jobs(status="running")
            if not running_jobs:
                logger.info("No jobs running, stopping workers")
                self.stop()
                break

            time.sleep(5)

    def cleanup(self) -> None:
        """Final cleanup tasks."""
        logger.info("Running final cleanup")

        # Write final status
        self.write_status()

        # Aggregate all errors
        self.aggregate_errors()

        # Clean up control files
        for f in [self.stop_file, self.finish_current_file]:
            if f.exists():
                f.unlink()

        # Remove status file on clean exit
        status_file = self.control_dir / f"status_{self.slurm_job_id}.json"
        if status_file.exists():
            status_file.unlink()

        logger.info("Launcher shutdown complete")

    def _handle_signal(self, signum: int, _frame: object) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}")
        self.stop()
