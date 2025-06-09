from dotenv import load_dotenv

from dr_exp.job_db import BaseJobDB, LocalJobDB, SupabaseJobDB, JobDBConfig

load_dotenv()


def get_job_db_client(config: JobDBConfig) -> BaseJobDB:
    """Create JobDB client from config.

    Parameters
    ----------
    config : JobDBConfig
        Configuration object with explicit parameters.

    Returns
    -------
    BaseJobDB
        A job database instance (LocalJobDB or SupabaseJobDB).

    Raises
    ------
    ValueError
        If configuration is invalid.
    """

    config.validate()

    if config.mode in ["supabase_remote", "supabase_local"]:
        return SupabaseJobDB(config)
    else:
        return LocalJobDB(config)
