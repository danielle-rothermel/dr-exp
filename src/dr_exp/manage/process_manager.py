"""Process management interface for worker processes."""

import os
import multiprocessing as mp
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod

from .streamlined_worker import run_streamlined_worker


def run_worker_main(worker_id: str, work_dir: str) -> None:
    """Wrapper to execute the worker with base path from env."""
    base_path = os.environ.get("DR_EXP_BASE_PATH", "./job_data")
    run_streamlined_worker(base_path=base_path, work_dir=work_dir, worker_id=worker_id)


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
    def launch_worker(self, worker_id: str, gpu_id: str, base_dir: str) -> bool:
        """Launch a worker process.
        
        Parameters
        ----------
        worker_id : str
            Unique identifier for the worker.
        gpu_id : str
            GPU ID to assign to the worker.
        base_dir : str
            Base directory for worker files.
            
        Returns
        -------
        bool
            True if worker was launched successfully.
        """
        pass
    
    @abstractmethod
    def stop_all_workers(self) -> None:
        """Stop all running worker processes."""
        pass
    
    @abstractmethod
    def restart_worker(self, worker_id: str) -> bool:
        """Restart a specific worker process.
        
        Parameters
        ----------
        worker_id : str
            Identifier of the worker to restart.
            
        Returns
        -------
        bool
            True if worker was restarted successfully.
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
        
        # Extract base path from environment
        self.base_path = os.environ.get("DR_EXP_BASE_PATH", "./job_data")
    
    def launch_worker(self, worker_id: str, gpu_id: str, base_dir: str) -> bool:
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
                "worker_dir": worker_dir
            }
            
            return True
            
        except Exception as e:
            print(f"Error launching worker {worker_id}: {e}")
            return False
    
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
    
    def restart_worker(self, worker_id: str) -> bool:
        """Restart a specific worker process."""
        info = self.workers.get(worker_id)
        if not info:
            return False
        
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
            
            return True
            
        except Exception as e:
            print(f"Error restarting worker {worker_id}: {e}")
            # Remove the failed worker
            self.workers.pop(worker_id, None)
            return False
    
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
                "pid": proc.pid if proc.is_alive() else None
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
    
    def launch_worker(self, worker_id: str, gpu_id: str, base_dir: str) -> bool:
        """Mock launch worker."""
        self.launch_count += 1
        self.workers[worker_id] = {
            "gpu": gpu_id,
            "base_dir": base_dir,
            "alive": True
        }
        return True
    
    def stop_all_workers(self) -> None:
        """Mock stop all workers."""
        self.stop_count += 1
        for worker_info in self.workers.values():
            worker_info["alive"] = False
    
    def restart_worker(self, worker_id: str) -> bool:
        """Mock restart worker."""
        if worker_id not in self.workers:
            return False
        
        self.restart_count += 1
        self.workers[worker_id]["alive"] = True
        return True
    
    def get_worker_count(self) -> int:
        """Get the total number of managed workers."""
        return len(self.workers)
    
    def get_worker_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status information for all workers."""
        return {
            worker_id: {
                "alive": info["alive"],
                "gpu": info["gpu"],
                "pid": 12345  # Mock PID
            }
            for worker_id, info in self.workers.items()
        }


__all__ = [
    "BaseProcessManager", 
    "ProcessManager", 
    "MockProcessManager",
    "run_worker_main"
]