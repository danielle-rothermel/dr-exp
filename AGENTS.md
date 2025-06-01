# AGENTS.md: Quick Guide for Agentic Development (dr_exp)

## 1. Purpose
This guide directs agentic coders in developing the Experiment Manager (`dr_exp`). For full details, always refer to `docs/product_requirement_doc.md` and component-specific spec files in `docs/`.

## 2. Core Principles for Agent Collaboration
* **Clarity is Key:** Use precise instructions. Reference spec documents.
* **Iterate & Review:** Expect revisions. Review agent output frequently.
* **Context Matters:** Provide necessary existing code/interfaces.
* **Test Rigorously:** Request unit tests from agents; perform independent testing.
* **Human Oversight:** Agents assist; humans own architecture and quality.

## 3. On Every Change

First, lint your changes and fix any issues:
```
uv run ruff check . --fix
```

Then format all python files:
```
uv run ruff format
```

Finally, run the test suite from the top level and fix any issues:
```
uv run pytest
```

## 4. Simplified Agent Workflow (for Phase 1 Tasks)
2.  **Understand Specs:** Thoroughly read the primary spec document for the component (e.g., `docs/supabase_mock.md`) and relevant sections of `docs/product_requirement_doc.md`.
3.  **Code & Test:** Implement the component in Python. Write `pytest` unit tests covering its specified behavior.
4.  **Review & Iterate:** Submit code and tests for human review. Revise based on feedback.
5.  **Integrate (Locally):** Human developer ensures the component can be (or will be) integrated with other Phase 1 mock components.

### 5. Phase 2 Tasks

#### Task 2.1 Finalize Structured Logger Implementation

Objective:
Finalize the implementation of the `StructuredLogger` Python class based on the full specifications in `docs/logger.md`. This involves ensuring all features, error handling, and concurrency considerations outlined in the spec are robustly implemented.

Primary Specification Document:
- `docs/logger.md`

Recap of Key Functionalities to Implement/Verify (refer to spec for full details):
- [x]  `__init__(self, cfg: DictConfig, compress_checkpoints: bool = False, debug: bool = False)`: Ensure robust initialization using `cfg.logging` paths.
- [x]  `log(self, metrics: dict)`: Append JSON-serializable metrics to `metrics.jsonl`, inject timestamp and run ID, handle buffering/flushing if specified.
- [x]  `save_checkpoint(self, state_dict: dict, tag: str)`: Save checkpoint to `cfg.logging.checkpoint_dir` with correct naming and optional Gzip compression. Log metadata to internal registry.
- [x]  `log_artifact(self, path: str)`: Register an existing file or directory path to be tracked.
- [x]  `finalize(self) -> dict`: Close log file, flush buffers, return summary metadata (metrics_path, num_metrics, artifact_paths, num_checkpoints, finalize_success). Must be idempotent.
- [x]  Error Handling: Implement behavior for `debug=True` (raise exceptions) and `debug=False` (log errors to `logger_error.log`, attempt safe continuation).
- [x]  Concurrency: Ensure methods are safe for potential multiprocessing usage (though the primary design is one logger instance per worker with unique paths, ensure no internal race conditions if methods could be called rapidly). File-level locks or safe append mechanisms for any shared resources (if any, though ideally none for unique-path logger).
- [x]  Path Management: Strictly use paths provided in `cfg.logging` (e.g., `cfg.logging.out_path`, `cfg.logging.checkpoint_dir`, `cfg.logging.artifact_dir`). These paths will be unique per worker instance.

Expected Output:
- Updated `structured_logger.py` file with the complete implementation.
- Comprehensive `pytest` unit tests in `tests/test_logger.py` covering all functionalities, including different configurations (compression, debug mode), error conditions, and output validation.

Considerations:
- The logger does NOT handle uploads to Supabase; this is the Worker's responsibility.
- The logger should remain agnostic to the training framework.
- Ensure all file I/O operations are robust (e.g., handle file not found, permissions issues gracefully when `debug=False`).

#### Task 2.2 Impelment Initial FastAPI Backend

Objective:
Implement the initial FastAPI backend server as specified in `docs/api_contracts.md`. This version will interact with the `SupabaseMockClient` (from Phase 1) to serve data and handle basic job control commands. Focus on the REST API endpoints.

Primary Specification Document:
- `docs/api_contracts.md`
- Refer to `docs/supabase_schema.md` for understanding the structure of data being handled (e.g., job records, configs).

Key Functionalities to Implement (interacting with `SupabaseMockClient`):
 - [x]  FastAPI application setup (`main.py` or similar).
 - [x]  REST API Endpoints:
    - [x] `GET /job/{job_id}`: Retrieve and return full job metadata (from mock job JSON files).
    - [x] `GET /config/{job_id}`: Retrieve and return the resolved Hydra config for a job (from mock job JSON files, assuming config is stored there or linked).
    - [x]`GET /metrics/{run_id}`:
        - Retrieve and return summarized metrics for a given run.
        - For V1 with mock client: Parse the `metrics.jsonl` file from `mock_storage/run_<run_id>/metrics.jsonl`.
        - Implement basic summarization (e.g., last N points, or all points if small).
        - Implement in-memory LRU caching for parsed metrics results to improve performance for repeated requests.
    - [x] `POST /job/kill`:
        - Simulate flagging a job for termination. This should update the corresponding job's JSON file in `mock_db/jobs/` (e.g., add a `kill_requested: true` flag or update status).
        - Implement basic API key authentication for this admin-only endpoint (read key from env var, check against a fixed value for now).
    - [x] `POST /job/requeue`:
        - Simulate requeuing a job. This should update the job's JSON file in `mock_db/jobs/` (e.g., set `status='queued'`, increment `retry_index`).
        - Implement basic API key authentication.
 - [x] Use Pydantic models for request/response validation and serialization.
 - [x]  Basic error handling and appropriate HTTP status code responses.

Expected Output:
- Python files for the FastAPI application (e.g., `main.py`, `routers/jobs.py`, `models.py`).
- `pytest` unit tests for API endpoints, testing responses, status codes, and interaction with a `SupabaseMockClient` instance.
- A `requirements.txt` update for FastAPI, Uvicorn, Pydantic.

Considerations:
- WebSocket endpoints are optional for this initial phase (as per PRD Phase 2 focus).
- Focus on clear API contracts and data transformation.
- Audit logging for admin actions (kill/requeue) should log to console/standard Python logger.

#### Task 2.3 Implement Core Worker Process Logic

Objective:
Implement the core logic for the `Worker Process` (`run_worker.py`) as specified in `docs/worker.md`. This script will claim jobs, execute a mock training process, log outputs, and simulate uploading results, all interacting with the `SupabaseMockClient` and the `StructuredLogger`.

Primary Specification Document:
- `docs/worker.md`
- Refer to Training Interface Contract (PRD Section 5).

Key Functionalities to Implement:
- [ ]  **Job Claiming:**
    - Use `SupabaseMockClient.claim_job()` to atomically claim a job.
    - Implement exponential backoff if no job is available initially. Exit if no job claimed after N retries.
- [ ]  **Configuration & Setup:**
    - On successful claim, retrieve the `config_json` for the job using `SupabaseMockClient.get_config_for_job()`.
    - Assume the SLURM Manager (or a test harness for now) provides unique local working directory paths. Inject these paths into `cfg.logging` (e.g., `out_path`, `checkpoint_dir`, `artifact_dir`).
    - Initialize `StructuredLogger` with this modified `cfg`.
- [ ]  **Execution:**
    - Call the `Mock Trainer`'s `train(cfg, logger)` function (from Phase 1).
    - Periodically update the job's `heartbeat` timestamp in the mock Supabase using `SupabaseMockClient.update_job()`.
- [ ]  **Result Handling & Upload (Simulated):**
    - After `train()` completes, call `logger.finalize()` to get metadata about local outputs.
    - Use `SupabaseMockClient.upload_artifact()` to "upload" the generated `metrics.jsonl`, checkpoints, and any other artifacts from their local paths (provided by logger) to the mock storage.
    - Use `SupabaseMockClient.upload_artifact()` to also "upload" the worker's own operational log file.
- [ ]  **Job Finalization:**
    - Update the job record in mock Supabase using `SupabaseMockClient.finalize_job()` or `update_job()` with the final status (from `train()` return or error), metrics from `train()`, paths to artifacts in mock storage, `upload_complete_at`, and `finalize_success`.
- [ ]  **Failure Handling:**
    - If `train()` raises an exception or returns a failure status, record the error using `SupabaseMockClient.record_failure()`.
    - Ensure job status is correctly updated to `failed`.
- [ ]  **Local Path Management:** The worker receives unique local paths for its outputs. It is responsible for cleaning up its local temporary working directory upon completion or critical failure.

Expected Output:
- `run_worker.py` script.
- `pytest` unit tests for the worker's core logic, mocking its dependencies (`SupabaseMockClient`, `StructuredLogger`, `Mock Trainer`) to test different scenarios (successful run, failed run, job claim failure, etc.).

Considerations:
- The worker itself does not implement retry logic for a failed `train()` call; requeuing is external.
- This version does not need to handle SLURM-specifics; it's the core job processing loop.
- Interaction with `SupabaseMockClient` is key.
