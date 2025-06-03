# FastAPI Mock Specification (`docs/api_mock.md`)

## Purpose

This mock provides a minimal local replacement for the FastAPI backend. It is intended for agent-based and offline development where:

* No internet connection is available
* The real FastAPI deployment is unavailable or undesired
* Simulated testing of the UI or CLI interface is needed

The mock returns fake or precomputed data that mirrors expected API responses.

---

## Scope

* Emulate REST API endpoints (e.g., `/job/{id}`, `/metrics/{id}`)
* Do not implement WebSocket functionality (UI will fall back to polling)
* Provide static or mock responses
* Optional: record API usage to test UI/backend integration

---

## Supported Endpoints

### `GET /job/{job_id}`

Returns mocked job metadata from a local JSON file or dictionary.

### `GET /config/{job_id}`

Returns a dummy Hydra-resolved config.

### `GET /metrics/{job_id}`

Returns a list of metric dictionaries loaded from `mock_storage/run_<job_id>/metrics.jsonl`.

### `POST /job/kill`

Logs job kill request locally but does not perform real action.

### `POST /job/requeue`

Logs requeue request and returns success. No real Supabase update.

---

## File Layout (Example)

```
api_mock/
  mock_db/
    jobs/
      <job_id>.json
    configs/
      <job_id>.json
    metrics/
      <job_id>.jsonl
  mock_server.py
```

---

## Implementation Strategy

* Use FastAPI with `TestClient` to run in-process
* Define endpoint routes and return mocked responses
* Optional: add logging middleware to trace calls
* Optional: auto-generate dummy metrics for live plot testing

---

## Optional Extensions

* Add query filtering support (e.g., `GET /jobs?status=failed`)
* Implement simple in-memory WebSocket simulator for dev testing
* Mirror Supabase failures for robustness testing

