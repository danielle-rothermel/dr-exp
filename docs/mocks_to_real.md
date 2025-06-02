# Switching from Mock Components to Real Components (`docs/mocks_to_real.md`)

## Overview
The project provides local mock implementations of Supabase, the FastAPI backend, and the training loop. These enable offline development and testing. When you are ready to run against the real services you can swap each mock for its corresponding real component by adjusting a few environment variables and, for the worker, providing your actual `train()` function.

## 1. Supabase Client
- The helper :func:`get_supabase_client` checks the environment variable `EXPMGR_MODE`.
- `EXPMGR_MODE=mock` (default) instantiates :class:`SupabaseMockClient` which reads and writes to `mock_db/` and `mock_storage/` under `DR_EXP_BASE_PATH`.
- `EXPMGR_MODE=real` instantiates :class:`SupabaseClient`. You must also set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (or `SUPABASE_KEY`).
- All CLI utilities, the FastAPI backend, and the manager call `get_supabase_client`, so this single flag controls the entire stack.

### Functional Differences
- **Mock:** jobs, metrics, and artifacts are stored on the local filesystem. No network access is required and concurrency handling is simplified.
- **Real:** every operation is sent to Supabase and its object storage. Job claiming, metric logging, and artifact uploads use real network calls and persist in your Supabase project.

## 2. FastAPI Backend
- The backend also relies on `EXPMGR_MODE` when calling `get_supabase_client`.
- With `EXPMGR_MODE=mock`, endpoints serve data from the local mock files (see `docs/api_mock.md`).
- With `EXPMGR_MODE=real`, the same endpoints interact with Supabase via :class:`SupabaseClient`.

## 3. Worker and Training Function
- `scripts/run_worker.py` exposes a `run_worker` function whose `trainer_fn` argument defaults to `dr_exp.mock.mock_trainer.train`.
- To run real training, invoke `run_worker` (or the manager) with your own training function passed to `trainer_fn`.
- The worker itself still obeys `EXPMGR_MODE`, so in real mode it logs and uploads through :class:`SupabaseClient`.

### Functional Differences
- **Mock trainer:** sleeps briefly, logs deterministic metrics, and produces dummy artifacts.
- **Real trainer:** performs actual training and generates real outputs which are uploaded to Supabase.

## 4. Manager and CLI Tools
- `scripts/run_manager.py` and scripts such as `upload_configs.py` call `get_supabase_client`, so they automatically switch according to `EXPMGR_MODE`.
- When using mocks you can set `DR_EXP_BASE_PATH` to choose where `mock_db/` and `mock_storage/` are created. In real mode this variable is ignored.

## 5. Switching Steps
1. Create a `.env` file with your Supabase credentials:
   ```bash
   SUPABASE_URL="your_supabase_project_url"
   SUPABASE_SERVICE_ROLE_KEY="your_supabase_service_role_key"
   EXPMGR_MODE="real"
   ```
2. Load these variables (e.g., using `python-dotenv`).
3. Start the FastAPI backend and manager with the same environment. Workers will now talk to Supabase and, if you supplied a real `trainer_fn`, run the real training code.
4. To return to offline development simply set `EXPMGR_MODE=mock` and optionally `DR_EXP_BASE_PATH` for the mock locations.

