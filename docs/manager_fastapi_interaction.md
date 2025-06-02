# Manager & FastAPI Backend Interaction (`docs/manager_fastapi_interaction.md`)

## Purpose

Describe how the SLURM manager (`scripts/run_manager.py`) cooperates with the FastAPI backend. The two components do not talk to each other directly; instead they share state via Supabase tables and storage. This document summarises the expected data flow and responsibilities on both sides.

## Overview

* `scripts/run_manager.py` launches workers, monitors heartbeats and updates job records in Supabase.
* The FastAPI backend exposes REST endpoints which read or modify these same Supabase records.
* Actions triggered by the UI or CLI through the FastAPI API (e.g. job kill or requeue) result in Supabase updates that the manager or workers react to.

## Manager Responsibilities

The product requirements document lists what the SLURM manager must do:

```text
- Parses `CUDA_VISIBLE_DEVICES` or similar to discover allocated GPUs.
- Creates a unique base directory for this SLURM job instance locally.
- Logs its own operational events to a file within its unique job directory.
- For each allocated GPU (or as configured), spawns N `Worker Process` instances.
- Monitors `Worker Process` heartbeats (read from Supabase `jobs` table).
- If a worker is detected as stalled/crashed (missed heartbeats):
    - Logs the event.
    - Marks the job the worker was handling as `failed` in Supabase.
    - Restarts a new worker process, which will attempt to claim a new job.
- Handles SLURM termination signals for graceful shutdown of workers.
- Exits if idle for a configurable timeout.
```

These responsibilities are detailed in the requirements document around lines 106‑117【F:docs/product_requirement_doc.md†L106-L117】.

## FastAPI Backend Responsibilities

The FastAPI backend exposes job information and control APIs. The same document summarises its role:

```text
1. React Babysitter UI:
    - Fetches job lists, statuses, configs, and metric summaries from the FastAPI backend.
    - Displays live metric plots (initially via polling `GET /metrics/{run_id}`).
    - Allows users (with admin rights) to trigger `kill` or `requeue` actions for jobs.
    - Failed jobs are highlighted.
2. FastAPI Backend:
    - `GET /job/{job_id}`: Returns job metadata.
    - `GET /config/{job_id}`: Returns job configuration.
    - `GET /metrics/{run_id}`: Returns summarized metrics.
    - `POST /job/kill`: (Admin) Sets a kill flag in the Supabase `jobs` record.
    - `POST /job/requeue`: (Admin) Updates job status to `queued`, increments `retry_index`.
```

These expectations come from lines 155‑167 of the requirements document【F:docs/product_requirement_doc.md†L155-L167】.

Further API details are provided in the API contracts file, for example the `POST /job/kill` description:

```text
### `POST /job/kill`
Flags a job for termination via Supabase.
* **Input**: `{"job_id": "abc-123"}`
* **Access**: Admin only (API key required)
* **Behavior**: Updates Supabase to set job kill flag. Workers will poll for this flag and terminate gracefully.
```

Lines 23‑37 in `docs/api_contracts.md` specify this behaviour【F:docs/api_contracts.md†L23-L37】.

## Interaction Pattern

1. The manager and its workers communicate only with Supabase. They never call the FastAPI server directly.
2. When the manager spawns a worker, the worker claims a job from the Supabase `jobs` table and updates `status` and `heartbeat` fields as training progresses.
3. The FastAPI backend reads these job records to answer `GET /job/{job_id}` and `GET /metrics/{run_id}` requests. Metrics are loaded from the same paths the worker uploaded to Supabase Storage.
4. When an administrator issues `POST /job/kill` or `POST /job/requeue`, the FastAPI backend updates the corresponding fields in Supabase. Workers or the manager observe these changes (e.g. the `kill_requested` flag) and act accordingly.
5. Secrets such as Supabase credentials for the manager and the FastAPI admin API key are provided via environment variables as described in the requirements document【F:docs/product_requirement_doc.md†L196-L201】.

## Summary

The manager updates Supabase with job status, heartbeats and artifact locations. The FastAPI backend reads and modifies that same data to provide UI and CLI functionality. No direct network calls between manager and backend are required—their interaction is mediated entirely by Supabase.
