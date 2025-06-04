# Job Database Clients

This package contains the database clients used by the manager, workers and the
backend.

- `supabase_job_db.py` – client implementation for real Supabase.
- `local_job_db.py` – filesystem-backed client for local development.

Structured logging utilities are located in :mod:`dr_exp.logging`.
