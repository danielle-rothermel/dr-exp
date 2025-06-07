"""Streamlined factory for creating integrated system components."""

import os
from typing import Optional, List
from dotenv import load_dotenv

from dr_exp.job_db import BaseJobDB, JobDBConfig
from dr_exp.manage.streamlined_manager import StreamlinedManager
from dr_exp.manage.streamlined_worker import run_streamlined_worker
from dr_exp.manage.process_manager import ProcessManager, BaseProcessManager
from .jobdb_factory import get_job_db_client

load_dotenv()


class SystemConfig:
    """Configuration for the streamlined experiment management system."""
    
    def __init__(
        self,
        # Job database configuration
        job_db_config: Optional[JobDBConfig] = None,
        
        # Manager configuration
        gpus: Optional[List[str]] = None,
        workers_per_gpu: int = 1,
        heartbeat_timeout: int = 60,
        idle_timeout_mins: int = 30,
        manager_base_dir: Optional[str] = None,
        
        # Worker configuration
        max_claim_attempts: int = 5,
        worker_heartbeat_interval: float = 5.0,
        
        # Process management
        multiprocessing_start_method: str = "fork"
    ):
        """Initialize system configuration.
        
        Parameters
        ----------
        job_db_config : JobDBConfig, optional
            Job database configuration. If None, created from environment.
        gpus : List[str], optional
            List of GPU IDs. If None, auto-discovered from environment.
        workers_per_gpu : int, optional
            Number of worker processes per GPU, by default 1.
        heartbeat_timeout : int, optional
            Manager heartbeat timeout in seconds, by default 60.
        idle_timeout_mins : int, optional
            Manager idle timeout in minutes, by default 30.
        manager_base_dir : str, optional
            Base directory for manager logs. If None, uses job_data/manager.
        max_claim_attempts : int, optional
            Worker job claiming attempts, by default 5.
        worker_heartbeat_interval : float, optional
            Worker heartbeat interval in seconds, by default 5.0.
        multiprocessing_start_method : str, optional
            Multiprocessing start method, by default "fork".
        """
        self.job_db_config = job_db_config or JobDBConfig.from_env()
        self.gpus = gpus or self._discover_gpus()
        self.workers_per_gpu = workers_per_gpu
        self.heartbeat_timeout = heartbeat_timeout
        self.idle_timeout_mins = idle_timeout_mins
        self.manager_base_dir = manager_base_dir or self._get_manager_base_dir()
        self.max_claim_attempts = max_claim_attempts
        self.worker_heartbeat_interval = worker_heartbeat_interval
        self.multiprocessing_start_method = multiprocessing_start_method
    
    def _discover_gpus(self) -> List[str]:
        """Auto-discover available GPUs from environment."""
        env = os.environ.get("CUDA_VISIBLE_DEVICES")
        if env:
            return [g.strip() for g in env.split(",") if g.strip()]
        
        # Default to single GPU if no environment variable
        return ["0"]
    
    def _get_manager_base_dir(self) -> str:
        """Get manager base directory from job database config."""
        base_path = self.job_db_config.base_path
        return os.path.join(base_path, "manager")
    
    def validate(self) -> None:
        """Validate the configuration."""
        self.job_db_config.validate()
        
        if not self.gpus:
            raise ValueError("At least one GPU must be specified")
        
        if self.workers_per_gpu < 1:
            raise ValueError("workers_per_gpu must be at least 1")
        
        if self.heartbeat_timeout < 10:
            raise ValueError("heartbeat_timeout must be at least 10 seconds")
        
        if self.worker_heartbeat_interval < 0.1:
            raise ValueError("worker_heartbeat_interval must be at least 0.1 seconds")
        
        if self.worker_heartbeat_interval >= self.heartbeat_timeout:
            raise ValueError("worker_heartbeat_interval must be less than heartbeat_timeout")


class StreamlinedFactory:
    """Factory for creating streamlined system components."""
    
    def __init__(self, config: Optional[SystemConfig] = None):
        """Initialize the factory with system configuration.
        
        Parameters
        ----------
        config : SystemConfig, optional
            System configuration. If None, creates default configuration.
        """
        self.config = config or SystemConfig()
        self.config.validate()
        
        # Shared job database instance
        self._job_db: Optional[BaseJobDB] = None
        self._process_manager: Optional[BaseProcessManager] = None
    
    @property
    def job_db(self) -> BaseJobDB:
        """Get or create shared job database instance."""
        if self._job_db is None:
            self._job_db = get_job_db_client(self.config.job_db_config)
        return self._job_db
    
    @property
    def process_manager(self) -> BaseProcessManager:
        """Get or create shared process manager instance."""
        if self._process_manager is None:
            self._process_manager = ProcessManager(
                start_method=self.config.multiprocessing_start_method
            )
        return self._process_manager
    
    def create_manager(self) -> StreamlinedManager:
        """Create a streamlined manager instance.
        
        Returns
        -------
        StreamlinedManager
            Configured manager instance ready to run.
        """
        return StreamlinedManager(
            gpus=self.config.gpus,
            workers_per_gpu=self.config.workers_per_gpu,
            heartbeat_timeout=self.config.heartbeat_timeout,
            idle_timeout_mins=self.config.idle_timeout_mins,
            base_dir=self.config.manager_base_dir,
            client=self.job_db,
            process_manager=self.process_manager
        )
    
    def run_worker(
        self,
        worker_id: str = "streamlined_worker",
        work_dir: Optional[str] = None,
        target_job_id: Optional[str] = None,
        respect_reservations: bool = True
    ) -> str:
        """Run a streamlined worker instance.
        
        Parameters
        ----------
        worker_id : str, optional
            Worker identifier, by default "streamlined_worker".
        work_dir : str, optional
            Work directory. If None, creates temporary directory.
        target_job_id : str, optional
            Specific job ID to target. If None, claims any available job.
        respect_reservations : bool, optional
            Whether to respect job reservations, by default True.
        
        Returns
        -------
        str
            Final status of job execution.
        """
        return run_streamlined_worker(
            base_path=self.config.job_db_config.base_path,
            work_dir=work_dir,
            max_claim_attempts=self.config.max_claim_attempts,
            heartbeat_interval=self.config.worker_heartbeat_interval,
            client=self.job_db,
            worker_id=worker_id,
            target_job_id=target_job_id,
            respect_reservations=respect_reservations
        )
    
    def get_system_status(self) -> dict:
        """Get current system status information.
        
        Returns
        -------
        dict
            System status including job counts, worker capacity, etc.
        """
        running_jobs = self.job_db.list_running_jobs()
        has_queued = self.job_db.has_queued_jobs()
        queue_summary = self.job_db.get_queue_summary(limit=10) if has_queued else []
        stale_jobs = self.job_db.get_stale_jobs(self.config.heartbeat_timeout * 2)
        
        return {
            "configuration": {
                "gpus": self.config.gpus,
                "workers_per_gpu": self.config.workers_per_gpu,
                "total_worker_capacity": len(self.config.gpus) * self.config.workers_per_gpu,
                "heartbeat_timeout": self.config.heartbeat_timeout,
                "mode": self.config.job_db_config.mode
            },
            "job_status": {
                "running_jobs": len(running_jobs),
                "has_queued_jobs": has_queued,
                "queued_jobs_summary": len(queue_summary),
                "stale_jobs": len(stale_jobs)
            },
            "queue_preview": [
                {
                    "id": job.get("id"),
                    "priority": job.get("priority", 100),
                    "created_at": job.get("created_at")
                }
                for job in queue_summary[:5]
            ],
            "stale_jobs_preview": [
                {
                    "job_id": job.job_id,
                    "worker": job.assigned_worker,
                    "age_seconds": job.age_seconds
                }
                for job in stale_jobs[:5]
            ]
        }


def create_streamlined_system(config: Optional[SystemConfig] = None) -> StreamlinedFactory:
    """Create a streamlined experiment management system.
    
    This is the main entry point for creating a fully configured system
    with all components properly integrated.
    
    Parameters
    ----------
    config : SystemConfig, optional
        System configuration. If None, uses environment defaults.
    
    Returns
    -------
    StreamlinedFactory
        Factory instance for creating managers and workers.
        
    Examples
    --------
    # Create system with defaults from environment
    system = create_streamlined_system()
    
    # Run a manager
    manager = system.create_manager()
    manager.run()
    
    # Run a worker
    status = system.run_worker(worker_id="worker_1")
    
    # Get system status
    status = system.get_system_status()
    """
    return StreamlinedFactory(config)


__all__ = [
    "SystemConfig",
    "StreamlinedFactory", 
    "create_streamlined_system"
]