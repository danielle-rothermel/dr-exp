"""Base class for job database clients."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseJobDB(ABC):
    """Abstract base class for job database clients.
    
    This class defines the interface that all job database implementations
    must provide for interacting with jobs, configurations, and artifacts.
    Includes support for priority-based job scheduling and queue management.
    """
    
    # Required attributes that subclasses must provide
    jobs_dir: str
    storage_dir: str
    
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


__all__ = ["BaseJobDB"]