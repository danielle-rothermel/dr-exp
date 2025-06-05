import os

from dotenv import load_dotenv

from dr_exp.job_db.base_job_db import BaseJobDB
from dr_exp.job_db.supabase_job_db import SupabaseJobDB
from dr_exp.job_db.local_job_db import LocalJobDB

load_dotenv()


def get_supabase_client(
    base_path: str = ".",
) -> BaseJobDB:
    """Instantiate either a Supabase or local job database client.

    Parameters
    ----------
    base_path : str, optional
        Base directory used when creating :class:`LocalJobDB` and as the
        local storage path when running in real mode.

    Returns
    -------
    BaseJobDB
        A job database instance depending on the ``EXPMGR_MODE`` environment
        variable.

    Raises
    ------
    ValueError
        If real mode is requested but no URL or key is provided.
    """
    mode = os.environ.get("EXPMGR_MODE", "mock").lower()
    if mode == "real":
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
            "SUPABASE_KEY"
        )
        if not url or not key:
            raise ValueError("SUPABASE_URL and key required for real mode")
        return SupabaseJobDB(url, key, base_path=base_path)
    return LocalJobDB(
        base_path=base_path, storage_path=os.path.join(base_path, "storage")
    )
