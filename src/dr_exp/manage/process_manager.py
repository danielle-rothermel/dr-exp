"""Process management interface for worker processes."""

import logging
import os
import multiprocessing as mp
from typing import Dict, Optional, Any
from abc import ABC, abstractmethod

from .worker import run_worker


def run_worker_main(worker_id: str, work_dir: str) -> None:
    """Wrapper to execute the worker with base path from env."""
    if "DR_EXP_BASE_PATH" not in os.environ:
        raise RuntimeError(
            "DR_EXP_BASE_PATH environment variable is required but not set"
        )
    base_path = os.environ["DR_EXP_BASE_PATH"]
    run_worker(base_path=base_path, work_dir=work_dir, worker_id=worker_id)


def _worker_target(
    base_path: str, worker_id: str, gpu_id: str, worker_dir: str
) -> None:
    """Entry point for spawned worker processes."""
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu_id
    os.environ["DR_EXP_BASE_PATH"] = base_path
    os.makedirs(worker_dir, exist_ok=True)
    run_worker_main(worker_id=worker_id, work_dir=worker_dir)


class BaseProcessManager(ABC):
    """Abstract base class for process management."""

    @abstractmethod
    def launch_worker(self, worker_id: str, gpu_id: str, base_dir: str) -> None:
        """Launch a worker process.

        Parameters
        ----------
        worker_id : str
            Unique identifier for the worker.
        gpu_id : str
            GPU ID to assign to the worker.
        base_dir : str
            Base directory for worker files.

        Raises
        ------
        RuntimeError
            If worker launch fails.
        """
        pass

    @abstractmethod
    def stop_all_workers(self) -> None:
        """Stop all running worker processes."""
        pass

    @abstractmethod
    def restart_worker(self, worker_id: str) -> None:
        """Restart a specific worker process.

        Parameters
        ----------
        worker_id : str
            Identifier of the worker to restart.

        Raises
        ------
        RuntimeError
            If worker restart fails.
        """
        pass

    @abstractmethod
    def get_worker_count(self) -> int:
        """Get the total number of managed workers."""
        pass

    @abstractmethod
    def get_worker_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status information for all workers.

        Returns
        -------
        Dict[str, Dict[str, Any]]
            Mapping of worker_id to status information including:
            - alive: bool indicating if process is alive
            - gpu: str GPU ID assigned to worker
            - pid: int process ID (if available)
        """
        pass


class ProcessManager(BaseProcessManager):
    """Default multiprocessing-based process manager."""

    def __init__(self, start_method: Optional[str] = "fork") -> None:
        """Initialize the process manager.

        Parameters
        ----------
        start_method : str, optional
            Multiprocessing start method. Defaults to "fork".
        """
        self.workers: Dict[str, Dict[str, Any]] = {}

        try:
            self.ctx = (
                mp.get_context(start_method) if start_method else mp.get_context()
            )
        except ValueError:
            self.ctx = mp.get_context()

        # Extract base path from environment - fail fast if not configured
        if "DR_EXP_BASE_PATH" not in os.environ:
            raise RuntimeError(
                "DR_EXP_BASE_PATH environment variable is required for process management"
            )
        self.base_path = os.environ["DR_EXP_BASE_PATH"]

    def launch_worker(self, worker_id: str, gpu_id: str, base_dir: str) -> None:
        """Launch a worker process."""
        try:
            worker_dir = os.path.join(base_dir, worker_id)
            proc = self.ctx.Process(
                target=_worker_target,
                args=(self.base_path, worker_id, gpu_id, worker_dir),
            )
            proc.start()

            self.workers[worker_id] = {
                "process": proc,
                "gpu": gpu_id,
                "worker_dir": worker_dir,
            }

        except Exception as e:
            logging.error(f"Critical: Failed to launch worker {worker_id}: {e}")
            raise RuntimeError(
                f"Worker launch failed - system cannot operate with insufficient workers: {e}"
            ) from e

    def stop_all_workers(self) -> None:
        """Stop all running worker processes."""
        for worker_id, info in list(self.workers.items()):
            proc: mp.Process = info["process"]
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
                if proc.is_alive():
                    # Force kill if still alive
                    proc.kill()
                    proc.join(timeout=2)

        self.workers.clear()

    def restart_worker(self, worker_id: str) -> None:
        """Restart a specific worker process."""
        info = self.workers.get(worker_id)
        if not info:
            raise RuntimeError(f"Cannot restart worker {worker_id}: worker not found")

        try:
            # Stop the existing process
            proc: mp.Process = info["process"]
            gpu_id = info["gpu"]
            worker_dir = info["worker_dir"]

            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
                if proc.is_alive():
                    proc.kill()
                    proc.join(timeout=2)

            # Launch new process
            new_proc = self.ctx.Process(
                target=_worker_target,
                args=(self.base_path, worker_id, gpu_id, worker_dir),
            )
            new_proc.start()

            # Update worker info
            self.workers[worker_id]["process"] = new_proc

        except Exception as e:
            logging.error(f"Critical: Failed to restart worker {worker_id}: {e}")
            # Remove the failed worker
            self.workers.pop(worker_id, None)
            raise RuntimeError(
                f"Worker restart failed - infrastructure may be compromised: {e}"
            ) from e

    def get_worker_count(self) -> int:
        """Get the total number of managed workers."""
        return len(self.workers)

    def get_worker_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status information for all workers."""
        status = {}

        for worker_id, info in self.workers.items():
            proc: mp.Process = info["process"]
            status[worker_id] = {
                "alive": proc.is_alive(),
                "gpu": info["gpu"],
                "pid": proc.pid if proc.is_alive() else None,
            }

        return status


class MockProcessManager(BaseProcessManager):
    """Mock process manager for testing."""

    def __init__(self) -> None:
        """Initialize the mock process manager."""
        self.workers: Dict[str, Dict[str, Any]] = {}
        self.launch_count = 0
        self.restart_count = 0
        self.stop_count = 0

    def launch_worker(self, worker_id: str, gpu_id: str, base_dir: str) -> None:
        """Mock launch worker."""
        self.launch_count += 1
        self.workers[worker_id] = {"gpu": gpu_id, "base_dir": base_dir, "alive": True}

    def stop_all_workers(self) -> None:
        """Mock stop all workers."""
        self.stop_count += 1
        for worker_info in self.workers.values():
            worker_info["alive"] = False

    def restart_worker(self, worker_id: str) -> None:
        """Mock restart worker."""
        if worker_id not in self.workers:
            raise RuntimeError(f"Cannot restart worker {worker_id}: worker not found")

        self.restart_count += 1
        self.workers[worker_id]["alive"] = True

    def get_worker_count(self) -> int:
        """Get the total number of managed workers."""
        return len(self.workers)

    def get_worker_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status information for all workers."""
        return {
            worker_id: {
                "alive": info["alive"],
                "gpu": info["gpu"],
                "pid": 12345,  # Mock PID
            }
            for worker_id, info in self.workers.items()
        }


__all__ = [
    "BaseProcessManager",
    "ProcessManager",
    "MockProcessManager",
    "run_worker_main",
]
