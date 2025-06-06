import os
from typing import Optional

from dotenv import load_dotenv

from dr_exp.job_db import BaseJobDB, LocalJobDB, SupabaseJobDB, JobDBConfig

load_dotenv()


def get_job_db_client(config: Optional[JobDBConfig] = None) -> BaseJobDB:
    """Create JobDB client from config or environment.
    
    Parameters
    ----------
    config : JobDBConfig, optional
        Configuration object. If None, creates config from environment variables.
        
    Returns
    -------
    BaseJobDB
        A job database instance (LocalJobDB or SupabaseJobDB).
        
    Raises
    ------
    ValueError
        If configuration is invalid.
    """
    if config is None:
        config = JobDBConfig.from_env()
    
    config.validate()
    
    if config.mode == "real":
        return SupabaseJobDB(config)
    else:
        return LocalJobDB(config)


def get_supabase_client(base_path: str = ".") -> BaseJobDB:
    """Legacy factory function for backward compatibility.
    
    This function is deprecated. Use get_job_db_client() instead.
    
    Parameters
    ----------
    base_path : str, optional
        Base directory for job data storage.
        
    Returns
    -------
    BaseJobDB
        A job database instance.
    """
    config = JobDBConfig.from_env()
    config.base_path = base_path
    config.storage_path = os.path.join(base_path, "storage")
    return get_job_db_client(config)
