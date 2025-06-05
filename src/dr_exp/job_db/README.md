# Job Database Utilities

This package provides database helpers used by both the worker
processes and the FastAPI backend.

Modules
-------
- `local_job_db.py` – a filesystem-backed client that mimics Supabase for
  offline development and testing.
- `supabase_job_db.py` – a thin wrapper around the Supabase Python client
  used when running against a real Supabase instance.
- `__init__.py` exports :class:`~dr_exp.job_db.LocalDBClient`,
  :class:`~dr_exp.job_db.SupabaseClient`, and the
  :func:`~dr_exp.utils.jobdb_factory.get_supabase_client` helper.
