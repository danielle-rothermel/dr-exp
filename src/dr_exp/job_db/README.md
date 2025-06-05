# Job Database Utilities

This package provides database implementations used by both the worker
processes and the FastAPI backend. All implementations inherit from a
common base class that defines the job database interface.

Modules
-------
- `base_job_db.py` – abstract base class defining the job database interface
  that all implementations must follow.
- `local_job_db.py` – a filesystem-backed implementation that uses local JSON
  files for job storage. Ideal for offline development and testing.
- `supabase_job_db.py` – a cloud-backed implementation using Supabase for
  production job management and artifact storage.
- `__init__.py` exports :class:`~dr_exp.job_db.BaseJobDB`,
  :class:`~dr_exp.job_db.LocalJobDB`, :class:`~dr_exp.job_db.SupabaseJobDB`,
  and the :func:`~dr_exp.utils.jobdb_factory.get_supabase_client` factory helper.

Interface
---------
All job database implementations provide the following core functionality:

**Required Methods:**
- `claim_job()` – atomically claim the next available queued job
- `update_job()` – update job records with new data
- `get_job_details()` – retrieve full details for a specific job
- `get_config_for_job()` – get the configuration associated with a job
- `record_failure()` – record failure events and mark jobs as failed
- `finalize_job()` – finalize jobs with status and metadata
- `upload_artifact()` – upload artifacts to storage

**Optional Methods:**
- `list_jobs()` – return all job records (implemented by LocalJobDB)
- `add_job()` – add new job entries (implemented by LocalJobDB)  
- `log_metrics()` – log metrics for jobs (implemented by LocalJobDB)

**Attributes:**
- `jobs_dir` – directory for job data and metadata
- `storage_dir` – directory for artifacts and run outputs
