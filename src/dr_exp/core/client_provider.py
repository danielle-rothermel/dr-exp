import os
from typing import Union

from .supabase_client import SupabaseClient
from dr_exp.mock.supabase_mock_client import SupabaseMockClient


def get_supabase_client(
    base_path: str = ".",
) -> Union[SupabaseClient, SupabaseMockClient]:
    """Instantiate either a real or mock Supabase client.

    Parameters
    ----------
    base_path : str, optional
        Base directory used when creating :class:`SupabaseMockClient`. Ignored
        when running in real mode.

    Returns
    -------
    SupabaseClient | SupabaseMockClient
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
        return SupabaseClient(url, key)
    return SupabaseMockClient(base_path=base_path)
