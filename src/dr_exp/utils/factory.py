"""Factory for creating integrated system components."""

import os
from typing import Optional, List
from dotenv import load_dotenv
from pathlib import Path

from dr_exp.job_db import BaseJobDB, JobDBConfig
from dr_exp.manage.manager import Manager
from dr_exp.manage.worker import run_worker
from dr_exp.manage.process_manager import ProcessManager, BaseProcessManager
from dr_exp.utils.gpu_discovery import discover_gpus, validate_gpu_ids
from dr_exp.utils.cli_config import CLI_DEFAULTS
from .jobdb_factory import get_job_db_client

load_dotenv()


class SystemConfig:
    """Configuration for the experiment management system."""
    
    def __init__(
        self,
        # Job database configuration
        job_db_config: Optional[JobDBConfig] = None,
        
        # Manager configuration
        gpus: Optional[List[str]] = None,
        gpus_per_node: Optional[int] = None,  # Used for GPU discovery if gpus not provided
        workers_per_gpu: int = CLI_DEFAULTS.WORKERS_PER_GPU,
        heartbeat_timeout: int = CLI_DEFAULTS.HEARTBEAT_TIMEOUT,
        idle_timeout_mins: int = CLI_DEFAULTS.IDLE_TIMEOUT_MINS,
        manager_base_dir: Optional[str] = None,
        
        # Worker configuration
        max_claim_attempts: int = 5,
        worker_heartbeat_interval: float = 5.0,
        
        # Process management
        multiprocessing_start_method: str = CLI_DEFAULTS.DEFAULT_START_METHOD,
        
        # Environment-aware options
        auto_detect_environment: bool = True
    ):
        """Initialize system configuration.
        
        Parameters
        ----------
        job_db_config : JobDBConfig, optional
            Job database configuration. If None, created from environment.
        gpus : List[str], optional
            List of GPU IDs. If None, auto-discovered from environment.
        gpus_per_node : int, optional
            Number of GPUs for discovery if gpus not provided.
        workers_per_gpu : int, optional
            Number of worker processes per GPU.
        heartbeat_timeout : int, optional
            Manager heartbeat timeout in seconds.
        idle_timeout_mins : int, optional
            Manager idle timeout in minutes.
        manager_base_dir : str, optional
            Base directory for manager logs. If None, environment-aware default.
        max_claim_attempts : int, optional
            Worker job claiming attempts, by default 5.
        worker_heartbeat_interval : float, optional
            Worker heartbeat interval in seconds, by default 5.0.
        multiprocessing_start_method : str, optional
            Multiprocessing start method.
        auto_detect_environment : bool, optional
            Whether to auto-detect environment-specific settings.
        """
        self.job_db_config = job_db_config or JobDBConfig.from_env()
        self.gpus = gpus or self._discover_gpus(gpus_per_node or CLI_DEFAULTS.GPUS_PER_NODE)
        self.workers_per_gpu = workers_per_gpu
        self.heartbeat_timeout = heartbeat_timeout
        self.idle_timeout_mins = idle_timeout_mins
        self.manager_base_dir = manager_base_dir or self._get_manager_base_dir(auto_detect_environment)
        self.max_claim_attempts = max_claim_attempts
        self.worker_heartbeat_interval = worker_heartbeat_interval
        self.multiprocessing_start_method = multiprocessing_start_method
        self.auto_detect_environment = auto_detect_environment
    
    def _discover_gpus(self, gpus_per_node: int) -> List[str]:
        """Auto-discover available GPUs from environment."""
        gpus = discover_gpus(gpus_per_node)
        validate_gpu_ids(gpus)
        return gpus
    
    def _get_manager_base_dir(self, auto_detect: bool = True) -> str:
        """Get manager base directory with SLURM awareness."""
        base_path = self.job_db_config.base_path
        
        if auto_detect:
            # Check for SLURM environment
            slurm_job_id = os.environ.get("SLURM_JOB_ID")
            if slurm_job_id:
                return os.path.join(base_path, "manager_runs", f"job_{slurm_job_id}")
            
            # Use process ID as fallback for local development
            pid = os.getpid()
            return os.path.join(base_path, "manager_runs", f"pid_{pid}")
        
        # Default manager directory
        return os.path.join(base_path, "manager")
    
    def get_environment_info(self) -> dict:
        """Get information about the current execution environment.
        
        Returns
        -------
        dict
            Environment information including SLURM details.
        """
        info = {
            "scheduler": "local",
            "job_id": None,
            "node_name": os.environ.get("HOSTNAME", "unknown"),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "process_id": os.getpid()
        }
        
        # Check for SLURM
        if os.environ.get("SLURM_JOB_ID"):
            info.update({
                "scheduler": "slurm",
                "job_id": os.environ.get("SLURM_JOB_ID"),
                "job_name": os.environ.get("SLURM_JOB_NAME"),
                "node_list": os.environ.get("SLURM_JOB_NODELIST"),
                "task_count": os.environ.get("SLURM_NTASKS"),
                "cpus_per_task": os.environ.get("SLURM_CPUS_PER_TASK")
            })
        
        return info
    
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


class Factory:
    """Factory for creating system components."""
    
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
    
    def create_manager(self) -> Manager:
        """Create a manager instance.
        
        Returns
        -------
        Manager
            Configured manager instance ready to run.
        """
        return Manager(
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
        worker_id: str = "worker",
        work_dir: Optional[str] = None,
        target_job_id: Optional[str] = None,
        respect_reservations: bool = True
    ) -> str:
        """Run a worker instance.
        
        Parameters
        ----------
        worker_id : str, optional
            Worker identifier, by default "worker".
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
        return run_worker(
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
            System status including job counts, worker capacity, environment info, etc.
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
                "mode": self.config.job_db_config.mode,
                "manager_base_dir": self.config.manager_base_dir
            },
            "environment": self.config.get_environment_info(),
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


def create_system(config: Optional[SystemConfig] = None) -> Factory:
    """Create an experiment management system.
    
    This is the main entry point for creating a fully configured system
    with all components properly integrated.
    
    Parameters
    ----------
    config : SystemConfig, optional
        System configuration. If None, uses environment defaults.
    
    Returns
    -------
    Factory
        Factory instance for creating managers and workers.
        
    Examples
    --------
    # Create system with defaults from environment
    system = create_system()
    
    # Run a manager
    manager = system.create_manager()
    manager.run()
    
    # Run a worker
    status = system.run_worker(worker_id="worker_1")
    
    # Get system status
    status = system.get_system_status()
    """
    return Factory(config)


__all__ = [
    "SystemConfig",
    "Factory", 
    "create_system"
]