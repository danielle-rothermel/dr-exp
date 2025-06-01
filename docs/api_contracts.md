# FastAPI API Contracts (`docs/api_contracts.md`)

## Purpose

The FastAPI backend serves as a thin, asynchronous abstraction layer between Supabase and downstream consumers such as the React Babysitter UI, CLI tools, or workers. It also performs log summarization, caching, job control, and optional WebSocket broadcasting.

This document defines the expected endpoints, their inputs/outputs, security requirements, and behaviors.

---

## Core Responsibilities

* Provide safe access to Supabase via API key authentication
* Serve live or summarized metrics and logs to the UI
* Allow manual job control (e.g., kill, requeue) via admin-only endpoints
* Optionally cache expensive summaries for `.jsonl` parsing
* Stream real-time updates via WebSocket endpoints

---

## REST API Endpoints

### `GET /metrics/{run_id}`

Returns summarized metrics for a given run.

* **Input**: `run_id: str`
* **Output**: JSON summary of key metrics (e.g., final loss, accuracy, slopes)
* **Source**: Parses metrics `.jsonl` or reads from Supabase

### `POST /job/kill`

Flags a job for termination via Supabase.

* **Input**: `{"job_id": "abc-123"}`
* **Access**: Admin only (API key required)
* **Behavior**: Updates Supabase to set job kill flag. Workers will poll for this flag and terminate gracefully.

### `POST /job/requeue`

Requeues a failed or stalled job.

* **Input**: `{"job_id": "abc-123"}`
* **Access**: Admin only
* **Behavior**: Updates `status='queued'`, increments `retry_index`, logs a `failures` entry

### `GET /job/{job_id}`

Returns full job metadata.

* **Output**: JSON with job fields (status, config, start time, etc.)

### `GET /config/{job_id}`

Returns the resolved Hydra config for a job.

* **Output**: JSON config from Supabase `config_json`

---

## WebSocket Endpoints (Optional)

### `GET /ws/metrics/{run_id}`

Streams live training metrics for real-time UI plotting.

* **Behavior**: Forwards structured JSON log lines from `StructuredLogger` as they are written
* **Fallback**: If unavailable, UI will poll REST endpoint

---

## Authentication & Permissions

| Endpoint            | Access Scope | Enforcement                |
| ------------------- | ------------ | -------------------------- |
| `GET /metrics/*`    | Public       | None (read-only)           |
| `GET /job/*`        | Public       | None                       |
| `GET /config/*`     | Public       | None                       |
| `POST /job/kill`    | Admin only   | Requires API key in header |
| `POST /job/requeue` | Admin only   | Requires API key in header |

---

## Performance & Caching

* Metrics summaries may be cached in memory (e.g., Redis or in-process LRU cache)
* Parsing `.jsonl` logs should be offloaded from the UI
* Long `.jsonl` files should support pagination or downsampling for plotting

---

## Optional Extensions

* `POST /job/delete` — Marks a job as deleted, optionally purging blobs
* `GET /sweep/{cluster_id}/summary` — Aggregates results over a sweep
* `GET /artifacts/{job_id}` — Lists downloadable files for a run

---

## Implementation Notes

* Server: Uvicorn with FastAPI
* Deployment: Fly.io, Render, or local dev server
* All endpoints should support async handlers
* Use Pydantic models for validation and response formatting

---

## Design Decisions

1. `.jsonl` parsing should be performed on the fly
2. `/metrics/{run_id}` should return raw logs

