# Backend

FastAPI application serving REST endpoints for the Experiment Manager.

## Files

- `main.py` exposes the FastAPI `app` and the `MetricsLoader` helper.
- `models.py` defines Pydantic models shared between the backend and UI.

## Key Endpoints

- `GET /jobs` – list available jobs.
- `GET /job/{job_id}` – retrieve details for a specific job.
- `GET /config/{job_id}` – return the job configuration.
- `GET /metrics/{run_id}` – download the metrics JSONL for a run.
- `POST /job/kill` – mark a job as killed (admin only).
- `POST /job/requeue` – requeue a job for another attempt (admin only).
