from dr_exp.logging.structured_logger import StructuredLogger
from .local_job_db import LocalDBClient


def get_supabase_client(base_path: str = "."):
    """Lazy wrapper around :func:`dr_exp.utils.jobdb_factory.get_supabase_client`."""
    from dr_exp.utils import jobdb_factory

    return jobdb_factory.get_supabase_client(base_path=base_path)


__all__ = ["StructuredLogger", "get_supabase_client", "LocalDBClient"]
