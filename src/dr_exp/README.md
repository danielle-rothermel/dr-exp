# dr_exp Package

Core Python package implementing the backend, job database clients, manager logic and utilities.

Subpackages:
- `api/` – FastAPI backend serving the UI and workers.
- `job_db/` – Supabase and local database clients.
- `manage/` – manager and worker implementations.
- `logging/` – structured logging utilities.
- `train_examples/` – dummy trainer and Hydra configs.
- `utils/` – small helper utilities.
