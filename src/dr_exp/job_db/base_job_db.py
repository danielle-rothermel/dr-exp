"""Base class for job database clients."""

import os
from abc import ABC, abstractmethod
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class StaleJobInfo:
    """Information about a job with stale heartbeat."""
    job_id: str
    assigned_worker: str
    last_heartbeat: datetime
    age_seconds: int


class BaseJobDB(ABC):
    """Abstract base class for job database clients.
    
    This class defines the interface that all job database implementations
    must provide for interacting with jobs, configurations, and artifacts.
    Includes support for priority-based job scheduling and queue management.
    """
    
    def __init__(self, base_path: str = ".", storage_path: str = "./storage"):
        """Initialize common attributes for all job database implementations.
        
        Parameters
        ----------
        base_path : str, optional
            Base directory under which job data is stored, by default ".".
        storage_path : str, optional
            Directory for artifact and run output storage, by default "./storage".
        """
        self.base_path = os.path.abspath(base_path)
        self.storage_dir = os.path.abspath(storage_path)
        self.jobs_dir = os.path.join(self.base_path, "job_data")
        
        # Create directories if needed
        os.makedirs(self.jobs_dir, exist_ok=True)
        os.makedirs(self.storage_dir, exist_ok=True)
    
    @abstractmethod
    def claim_job(
        self, 
        worker_id: Optional[str] = None,
        respect_reservations: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Claim the next available queued job.
        
        Parameters
        ----------
        worker_id : str, optional
            Identifier of the worker claiming the job.
        respect_reservations : bool, optional
            Whether to respect job reservations, by default True.
            If True, reserved jobs can only be claimed by their designated worker.
            
        Returns
        -------
        dict[str, Any] | None
            The claimed job record or None if no job is available.
        """
        pass
    
    @abstractmethod
    def update_job(self, job_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a job record with new data.
        
        Parameters
        ----------
        job_id : str
            Identifier of the job to update.
        data : dict[str, Any]
            Fields to update on the job record.
            
        Returns
        -------
        dict[str, Any]
            A dictionary describing the outcome of the update operation.
        """
        pass
    
    @abstractmethod
    def get_job_details(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full details for a specific job.
        
        Parameters
        ----------
        job_id : str
            Identifier of the job to fetch.
            
        Returns
        -------
        dict[str, Any] | None
            The job record if found, otherwise None.
        """
        pass
    
    @abstractmethod
    def get_config_for_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return the configuration associated with a job.
        
        Parameters
        ----------
        job_id : str
            Job identifier whose config should be fetched.
            
        Returns
        -------
        dict[str, Any] | None
            The configuration dictionary or None if unavailable.
        """
        pass
    
    @abstractmethod
    def record_failure(
        self,
        job_id: str,
        error_type: str,
        message: str,
        stacktrace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a failure event and mark the job as failed.
        
        Parameters
        ----------
        job_id : str
            Identifier of the job that failed.
        error_type : str
            Short error class or type description.
        message : str
            Human-readable error message.
        stacktrace : str, optional
            Stack trace to store for debugging.
            
        Returns
        -------
        dict[str, Any]
            Result of the failure recording operation.
        """
        pass
    
    @abstractmethod
    def finalize_job(
        self, job_id: str, final_status: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Finalize a job with the given status and metadata.
        
        Parameters
        ----------
        job_id : str
            Identifier of the job.
        final_status : str
            Final status string to record.
        metadata : dict[str, Any]
            Additional fields to store on the job record.
            
        Returns
        -------
        dict[str, Any]
            Result of the finalization operation.
        """
        pass
    
    @abstractmethod
    def upload_artifact(
        self, job_id: str, local_path: str, remote_path_suffix: str
    ) -> Dict[str, Any]:
        """Upload an artifact file or directory.
        
        Parameters
        ----------
        job_id : str
            Job identifier.
        local_path : str
            Path to the local file or directory to upload.
        remote_path_suffix : str
            Relative path where the artifact should be stored.
            
        Returns
        -------
        dict[str, Any]
            Result of the upload operation including the storage path.
        """
        pass
    
    # =========================================================================
    # NEW STREAMLINED INTERFACE METHODS
    # =========================================================================
    
    @abstractmethod
    def list_running_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs currently in 'running' status.
        
        Eliminates the need for manager to implement database-specific 
        queries with file system traversal or SQL logic.
        
        Returns
        -------
        List[Dict[str, Any]]
            Jobs with status='running', including worker assignments
        """
        pass
    
    @abstractmethod
    def get_stale_jobs(self, max_age_seconds: int) -> List[StaleJobInfo]:
        """Find jobs with heartbeats older than max_age_seconds.
        
        Eliminates datetime parsing and comparison logic from manager.
        Manager just says "find stale jobs" and gets structured results.
        
        Parameters
        ----------
        max_age_seconds : int
            Maximum age of heartbeat before considering stale
            
        Returns
        -------
        List[StaleJobInfo]
            Structured information about stale jobs
        """
        pass
    
    @abstractmethod
    def mark_jobs_failed(
        self, 
        job_ids: List[str], 
        reason: str = "worker_lost"
    ) -> Dict[str, bool]:
        """Mark multiple jobs as failed efficiently.
        
        Eliminates the need for manager to loop through individual updates.
        Supports batch operations for better performance.
        
        Parameters
        ----------
        job_ids : List[str]
            Job IDs to mark as failed
        reason : str
            Failure reason for audit trail
            
        Returns
        -------
        Dict[str, bool]
            Mapping of job_id -> success status
        """
        pass
    
    @abstractmethod
    def has_queued_jobs(self) -> bool:
        """Check if there are any queued jobs available.
        
        Eliminates the need for manager to fetch and count job lists
        when checking idle conditions. Simple boolean check.
        
        Returns
        -------
        bool
            True if there are jobs in 'queued' status
        """
        pass
    
    @abstractmethod
    def get_queue_summary(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get summary of top queued jobs for logging.
        
        Eliminates manager having to know about priority ordering.
        Just asks for "top jobs in queue" for monitoring purposes.
        
        Parameters
        ----------
        limit : int
            Maximum number of jobs to return
            
        Returns
        -------
        List[Dict[str, Any]]
            Top queued jobs with id, priority, created_at
        """
        pass
    
    @abstractmethod
    def get_metrics(self, run_id: str, limit: Optional[int] = 500) -> List[Dict[str, Any]]:
        """Get metrics for a specific run.
        
        Parameters
        ----------
        run_id : str
            Identifier of the run to load metrics for.
        limit : int, optional
            Maximum number of recent metrics to return, by default 500.
            If None, returns all metrics.
            
        Returns
        -------
        List[Dict[str, Any]]
            List of metrics records for the run.
            
        Raises
        ------
        FileNotFoundError
            If metrics for the run do not exist.
        """
        pass
    
    # =========================================================================
    # END NEW INTERFACE METHODS
    # =========================================================================
    
    # Optional methods that subclasses may implement differently
    
    def list_jobs(self) -> List[Dict[str, Any]]:
        """Return a list of all job records.
        
        Returns
        -------
        list[dict[str, Any]]
            List of job records.
            
        Raises
        ------
        NotImplementedError
            If this method is not implemented by the subclass.
        """
        raise NotImplementedError("list_jobs not implemented for this client type")
    
    def add_job(
        self,
        job_config: Dict[str, Any],
        sweep_config_id: str,
        status: str = "queued",
        priority: int = 100,
    ) -> Dict[str, Any]:
        """Add a new job entry.
        
        Parameters
        ----------
        job_config : dict[str, Any]
            The job configuration.
        sweep_config_id : str
            Identifier for the sweep configuration.
        status : str, optional
            Initial job status, by default "queued".
        priority : int, optional
            Job priority for queue ordering (0-1000), by default 100.
            Higher values indicate higher priority.
            
        Returns
        -------
        dict[str, Any]
            The created job record.
            
        Raises
        ------
        NotImplementedError
            If this method is not implemented by the subclass.
        """
        raise NotImplementedError("add_job not implemented for this client type")
    
    def log_metrics(self, job_id: str, metrics_list: List[Dict[str, Any]]) -> None:
        """Log metrics for a job.
        
        Parameters
        ----------
        job_id : str
            Job identifier.
        metrics_list : list[dict[str, Any]]
            List of metrics to log.
            
        Raises
        ------
        NotImplementedError
            If this method is not implemented by the subclass.
        """
        raise NotImplementedError("log_metrics not implemented for this client type")
    
    # Priority management methods
    
    @abstractmethod
    def update_job_priority(
        self,
        job_id: str,
        new_priority: int,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update the priority of a job.
        
        Parameters
        ----------
        job_id : str
            Identifier of the job to update.
        new_priority : int
            New priority value (0-1000). Higher values indicate higher priority.
        reason : str, optional
            Optional reason for the priority change, for audit purposes.
            
        Returns
        -------
        dict[str, Any]
            Result of the priority update operation.
        """
        pass
    
    @abstractmethod
    def boost_job_priority(
        self,
        job_id: str,
        boost_amount: int = 100,
    ) -> Dict[str, Any]:
        """Boost the priority of a job by a specified amount.
        
        Parameters
        ----------
        job_id : str
            Identifier of the job to boost.
        boost_amount : int, optional
            Amount to add to the current priority, by default 100.
            Final priority will be clamped to valid range (0-1000).
            
        Returns
        -------
        dict[str, Any]
            Result of the priority boost operation including new priority.
        """
        pass
    
    @abstractmethod
    def list_jobs_by_priority(
        self,
        status_filter: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List jobs ordered by priority (highest first).
        
        Parameters
        ----------
        status_filter : list[str], optional
            Filter jobs by status (e.g., ["queued", "running"]).
            If None, all jobs are returned.
        limit : int, optional
            Maximum number of jobs to return. If None, all matching jobs.
            
        Returns
        -------
        list[dict[str, Any]]
            List of job records ordered by priority (highest first),
            then by submission time (oldest first) for equal priorities.
        """
        pass
    
    # Job reservation methods
    
    @abstractmethod
    def add_reserved_job(
        self,
        job_config: Dict[str, Any],
        sweep_config_id: str,
        reserved_for_worker: str,
        reservation_timeout: Optional[int] = 300,
        priority: int = 100,
        status: str = "queued",
    ) -> Dict[str, Any]:
        """Add a new job entry reserved for a specific worker.
        
        Parameters
        ----------
        job_config : dict[str, Any]
            The job configuration.
        sweep_config_id : str
            Identifier for the sweep configuration.
        reserved_for_worker : str
            Worker ID that can claim this job.
        reservation_timeout : int, optional
            Reservation timeout in seconds, by default 300 (5 minutes).
            If None, reservation never expires.
        priority : int, optional
            Job priority for queue ordering (0-1000), by default 100.
        status : str, optional
            Initial job status, by default "queued".
            
        Returns
        -------
        dict[str, Any]
            The created job record with reservation information.
        """
        pass

    # Common implementations that can be shared
    
    def finalize_job(self, job_id: str, final_status: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Finalize a job with the given status and metadata.
        
        This is a common implementation that can be overridden if needed.
        
        Parameters
        ----------
        job_id : str
            Identifier of the job.
        final_status : str
            Final status string to record.
        metadata : dict[str, Any]
            Additional fields to store on the job record.
            
        Returns
        -------
        dict[str, Any]
            Result of the finalization operation.
        """
        update_data = {
            "status": final_status,
            "end_time": datetime.now(UTC).isoformat() + "Z",
        }
        update_data.update(metadata)
        result = self.update_job(job_id, update_data)
        if result.get("success"):
            self._write_finished_flag(job_id)
        return result
    
    def _write_finished_flag(self, job_id: str) -> None:
        """Create an empty finished.flag file for a completed job.
        
        Parameters
        ----------
        job_id : str
            Job identifier for which to create the finished flag.
        """
        run_dir = os.path.join(self.storage_dir, f"run_{job_id}")
        os.makedirs(run_dir, exist_ok=True)
        flag_path = os.path.join(run_dir, "finished.flag")
        try:
            with open(flag_path, "w"):
                pass
        except Exception as e:
            print(f"Error writing finished flag for job {job_id}: {e}")
    
    def _clamp_priority(self, priority: int) -> int:
        """Ensure priority is within valid range (0-1000).
        
        Parameters
        ----------
        priority : int
            Priority value to clamp.
            
        Returns
        -------
        int
            Priority value clamped to valid range (0-1000).
        """
        return max(0, min(1000, priority))


__all__ = ["BaseJobDB", "StaleJobInfo"]