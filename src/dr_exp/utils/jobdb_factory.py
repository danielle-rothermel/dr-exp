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

    if config.mode in ["supabase_remote", "supabase_local"]:
        return SupabaseJobDB(config)
    else:
        return LocalJobDB(config)
