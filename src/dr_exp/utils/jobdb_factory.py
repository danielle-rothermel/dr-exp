import os
from typing import Union

from dotenv import load_dotenv

from dr_exp.job_db.supabase_job_db import SupabaseClient
from dr_exp.job_db.local_job_db import LocalDBClient

load_dotenv()


def get_supabase_client(
    base_path: str = ".",
) -> Union[SupabaseClient, LocalDBClient]:
    """Instantiate either a real or mock Supabase client.

    Parameters
    ----------
    base_path : str, optional
        Base directory used when creating :class:`LocalDBClient` and as the
        local storage path when running in real mode.

    Returns
    -------
    SupabaseClient | LocalDBClient
        A client instance depending on the ``EXPMGR_MODE`` environment
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
        return SupabaseClient(url, key, base_path=base_path)
    return LocalDBClient(base_path=base_path, storage_path=os.path.join(base_path, "storage"))
