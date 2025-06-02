# Experiment Manager: Product Requirements Document (PRD)
## 1. Introduction
### 1.1. System Purpose
- The Experiment Manager is a system designed to coordinate, execute, monitor, and track large-scale deep learning experiments, primarily on SLURM-managed GPU clusters. It facilitates efficient management of hyperparameter sweeps, robust job execution, centralized data collection, and real-time experiment oversight.
### 1.2. Goals
- **Efficient Experimentation:** Streamline the process of defining, launching, and managing numerous experimental runs, especially hyperparameter sweeps.
- **Robust Execution:** Ensure reliable job execution with capabilities for error detection, logging, and basic retry/resume mechanisms.
- **Centralized Data:** Provide a single source of truth for configurations, metadata, logs, metrics, and artifacts.
- **Real-time Monitoring:** Offer researchers visibility into ongoing experiments and control over job lifecycles via a web interface.
- **Reproducibility:** Capture sufficient metadata (code versions, configurations, environment details) to enable a high degree of reproducibility.
- **Agent-Ready Design:** Structure components and interfaces to be suitable for implementation by agentic coders.
### 1.3. Design Principles
- **Modularity:** Clear separation of concerns between components.
- **Researcher-Centricity:** Prioritize user (researcher) needs for control, visibility, and ease of debugging.
- **Framework Agnostic:** Minimize assumptions about the specific deep learning training framework used.
- **Explicit Interfaces:** Well-defined contracts between components.
- **Data Completeness:** Comprehensive metadata storage for traceability.
- **Simplified V1 Scope:** Focus on core functionality for a single user on a known SLURM cluster environment.
## 2. System Architecture
### 2.1. System Diagram (Simplified)
```plain text
  +----------------------+      +---------------------+      +---------------------+
  | Hydra Config         |----->| Supabase            |<---->| FastAPI Backend     |
  | Generator (CLI)      |      | (DB & Storage)      |      | (API & WebSockets)  |
  +----------------------+      +----------^----------+      +---------^-----------+
                                           |                           |
                                           | (Job Claim, Logging,      | (UI Data, Control)
                                           |  Artifacts, Heartbeats)   |
                                           |                           |
  +----------------------+      +----------+----------+      +--------+------------+
  | SLURM Job Submission |----->| SLURM Manager       |----->| Worker Process(es)  |<---> React Babysitter UI|
  | (sbatch script)      |      | (Per SLURM Job)     |      | (Run train(), Logs) |      | (Monitoring & Ctrl) |
  +----------------------+      +---------------------+      +----------+----------+      +---------------------+
                                                                       |
                                                                       | (Uses)
                                                              +--------+--------+
                                                              | StructuredLogger|
                                                              +-----------------+
                                                              | train(cfg, log) |
                                                              | (User Code)     |
                                                              +-----------------+
```
### 2.2. Major Components & Core Responsibilities
- **Component**
    - **Description**
        - **Key Interactions**
- **Config Generator**
    - (CLI Tool) Uses Hydra to generate resolved experiment configurations from base YAMLs and sweep definitions.
        - Writes sweep metadata and individual job configurations to Supabase.
- **Supabase**
    - (Backend Service) Central datastore (PostgreSQL) and object storage.
        - Stores configs, job metadata, metrics, errors, artifact paths. Hosts log files.
- **SLURM Manager**
    - (Python Script) Launched by SLURM `sbatch`. Manages worker processes on a given node/GPU allocation.
        - Discovers GPUs, spawns workers, monitors heartbeats, handles worker crashes.
- **Worker Process**
    - (Python Script) Claims a job from Supabase, sets up environment, runs `train()`, logs, uploads results.
        - Supabase (claim, update, log), `StructuredLogger`, User's `train()` function.
- **StructuredLogger**
    - (Python Class) Used by `train()` to log metrics, save checkpoints, and register artifacts to local disk.
        - Writes to unique local paths provided by the Worker.
- **FastAPI Backend**
    - (Python Web Server) Provides a REST API and WebSocket interface to Supabase data.
        - Supabase (read/write), React UI (serves data, handles control commands).
- **React Babysitter UI**
    - (Web Application) Frontend for monitoring job status, viewing logs/metrics, and controlling jobs.
        - FastAPI Backend (data fetching, command sending).
- **Mock Components**
    - (Various) Local mocks for Supabase, FastAPI, and `train()` to enable offline/agent-based development.
        - Used during development and testing phases.
## 3. Core Data & State Management (Supabase)
### 3.1. Database Schema Overview
- Supabase PostgreSQL will host tables for:
    - `sweep_config_clusters`: Groups of related sweeps.
    - `sweep_configs`: Individual resolved Hydra configurations with hashes and metadata.
    - `jobs`: Tracks training job instances, status (`queued`, `running`, `completed`, `failed`, `deleted`), assigned worker, retry counts, paths to outputs, final metrics, and reproducibility metadata.
    - `metrics` (SQL Table): Optional, populated by a post-run analysis job from `.jsonl` files for faster querying of aggregated/summarized metrics by the UI.
    - `errors`: Structured error messages and stack traces for failed jobs.
    - failures: Audit log for job retries.
    - (Detailed schema, including fields and indexes, is in docs/supabase_schema.md)
### 3.2. Storage Buckets
- Supabase Storage will be used for:
    - **`experiment-artifacts` bucket:**
        - `run_<job_uuid>/metrics.jsonl`: Raw structured logs from each job.
        - `run_<job_uuid>/checkpoints/checkpoint_<tag>.pt.gz`: Model checkpoints.
        - `run_<job_uuid>/artifacts/...`: Other artifacts like plots, logs.
        - `run_<job_uuid>/worker_logs/worker_<instance_id>.log`: Operational logs from the worker process itself.
        - `run_<job_uuid>/manager.log`: Operational logs from the SLURM Manager process for that job's allocation.
## 4. Key Operational Flows
### 4.1. Experiment Configuration & Launch
1. **User Action:** Researcher defines a base Hydra config (`.yaml`) and sweep parameters.
2. **Config Generator (`manager_cli upload-configs`):**
    - Parses base config and sweep arguments.
    - Generates all individual resolved configurations.
    - Hashes each configuration for deduplication.
    - Creates a `sweep_config_clusters` entry in Supabase (auto-named if not specified).
    - For each unique config, creates a `sweep_configs` entry.
    - For each `sweep_configs` entry, creates one or more `jobs` entries with `status='queued'`.
    - Stores code version (git hash) and interface version with sweep/job metadata.
3. **User Action:** Researcher submits one or more SLURM jobs using an `sbatch` script, specifying the number of nodes, GPUs, etc.
### 4.2. SLURM Job Execution (Manager & Worker Lifecycle)
1. **SLURM `sbatch` Script:**
    - Sets up the necessary environment (modules, Python environment).
    - Exports required secrets (Supabase URL/keys) as environment variables.
    - Launches the `SLURM Manager` script (`scripts/run_manager.py`) on the allocated node.
2. **SLURM Manager (`scripts/run_manager.py`):**
    - Parses `CUDA_VISIBLE_DEVICES` or similar to discover allocated GPUs.
    - Creates a unique base directory for this SLURM job instance locally (e.g., `/tmp/exp_mgr_slurm/<slurm_job_id>/`).
    - Logs its own operational events to a file within its unique job directory, later uploaded to `run_<job_uuid>/manager.log`.
    - For each allocated GPU (or as configured), spawns N `Worker Process` instances.
    - Monitors `Worker Process` heartbeats (read from Supabase `jobs` table).
    - If a worker is detected as stalled/crashed (missed heartbeats):
        - Logs the event.
        - Marks the job the worker was handling as `failed` in Supabase (e.g., `status_reason='worker_lost'`).
        - Restarts a new worker process, which will attempt to claim a new job.
    - Handles SLURM termination signals for graceful shutdown of workers.
    - Exits if idle for a configurable timeout (e.g., no claimable jobs for X minutes).
3. **Worker Process (`dr_exp.worker.run_worker`):**
    - **Job Claim:**
        - Queries Supabase for a `jobs` record with `status='queued'`, attempting to atomically update it to `status='running'` and set `assigned_worker` (using a DB transaction or `UPDATE ... RETURNING` with `SKIP LOCKED`). Uses exponential backoff on failed claim attempts.
        - If no job is claimed after several attempts, exits.
    - **Setup:**
        - Retrieves the `config_json` for the claimed job from Supabase.
        - The Manager provides a unique local working directory for this specific worker instance (e.g., `/tmp/exp_mgr_slurm/<slurm_job_id>/worker_<job_id>_<worker_instance_id>/`).
        - Worker logs its own operational data to a local file (e.g., `worker.log`) within this directory.
        - Injects unique local paths into the job's configuration (`cfg.logging`) for `StructuredLogger`:
            - `cfg.logging.out_path`: e.g., `.../worker_<job_id>_<instance_id>/metrics.jsonl`
            - `cfg.logging.checkpoint_dir`: e.g., `.../worker_<job_id>_<instance_id>/checkpoints/`
            - `cfg.logging.artifact_dir`: e.g., `.../worker_<job_id>_<instance_id>/artifacts/`
    - **Execution:**
        - Initializes `StructuredLogger` with these unique paths.
        - Calls the user's `train(cfg, logger)` function.
        - Periodically updates `heartbeat` timestamp in its `jobs` record in Supabase.
    - **Completion/Failure Handling (Post `train()`):**
        - Calls `logger.finalize()` to get paths to all locally written files.
        - **Uploads:**
            - Local `metrics.jsonl` to `run_<job_id>/metrics.jsonl` in Supabase Storage.
            - Contents of local `checkpoint_dir` to `run_<job_id>/checkpoints/` in Supabase Storage.
            - Contents of local `artifact_dir` to `run_<job_id>/artifacts/` in Supabase Storage.
            - Its own `worker.log` to `run_<job_id>/worker_logs/worker_<job_id>_<instance_id>.log`.
        - Updates the `jobs` record in Supabase with:
            - Final status (`completed` or `failed` based on `train()` outcome and upload success).
            - Metrics returned by `train()`.
            - Paths to artifacts in Supabase Storage.
            - `upload_complete_at` and `finalize_success` flags.
        - If `train()` fails or critical errors occur:
            - Logs error details (type, message, stacktrace) to the `errors` table in Supabase.
            - Sets job status to `failed`.
    - **Cleanup:** Deletes its local temporary working directory.
    - Exits.
### 4.3. Logging, Metrics & Artifact Handling
- **StructuredLogger:** Writes all outputs (metrics, checkpoints, artifact registrations) to the unique local paths provided by the Worker. It does __not__ interact with Supabase directly.
- **Worker:** Responsible for all uploads from its local temporary directory to Supabase Storage after `train()` completes.
- **Path Uniqueness:** Ensured by the SLURM Manager creating unique local directories for each worker instance, which are then used to derive paths for the StructuredLogger.
### 4.4. Monitoring & Control (UI & API)
1. **React Babysitter UI:**
    - Fetches job lists, statuses, configs, and metric summaries from the FastAPI backend.
    - Displays live metric plots (initially via polling `GET /metrics/{run_id}`, later potentially via WebSockets).
    - Allows users (with admin rights) to trigger `kill` or `requeue` actions for jobs.
    - Failed jobs are highlighted. Basic filtering and sorting of jobs.
2. **FastAPI Backend:**
    - `GET /job/{job_id}`: Returns job metadata.
    - `GET /config/{job_id}`: Returns job configuration.
    - `GET /metrics/{run_id}`: Returns summarized metrics. For V1, parses `.jsonl` from Supabase Storage on demand (with LRU caching). For V2, may query the `metrics` SQL table.
    - `POST /job/kill`: (Admin) Sets a kill flag in the Supabase `jobs` record. Workers periodically check this flag and terminate gracefully if set.
    - `POST /job/requeue`: (Admin) Updates job status to `queued`, increments `retry_index`.
    - Admin actions are logged (who performed the action).
### 4.5. Error Handling & Retries
- **Worker `train()` Errors:** Logged to Supabase `errors` table by the worker. Job marked `failed`.
- **Worker Process Crashes:** Detected by SLURM Manager via missed heartbeats. Job marked `failed` (e.g., `status_reason='worker_lost'`). Manager starts a new worker.
- **Supabase/Network Errors:** Workers and Managers use retry mechanisms with backoff for Supabase operations. Persistent failures lead to process exit and error logging.
- **Job Requeue:** Manual via UI/API. Creates a new job attempt by resetting status to `queued` and incrementing `retry_index`. The new attempt will use the same `config_id`.
- **Resume:** Jobs can be configured with `resumable_from_run_id` and `checkpoint_url`. Workers receiving `cfg.resume_from` are responsible for loading the checkpoint.
## 5. Training Interface Contract
- Training repositories must implement a `train` function with the following signature:
- ```plain text
  def train(cfg: DictConfig, logger: Optional[StructuredLogger] = None) -> dict:
      # ... training logic ...
      # Use logger.log(), logger.save_checkpoint(), logger.log_artifact()
      return {
          "final_val_acc": float,
          "final_train_loss": float,
          "num_epochs": int,
          "status": "success" | "nan_failure" | "crash" | "other_failure", # Standardized status strings
          # metrics_path, artifacts_path, num_checkpoints are handled by the worker based on logger.finalize()
      }
  ```
    - The `train` function uses the provided `logger` instance to record metrics and save checkpoints/artifacts to local paths.
    - The `cfg` object will include injected paths under `cfg.logging` for the logger to use.
## 6. Reproducibility Strategy
- **Configuration:** Full resolved Hydra configs stored in `sweep_configs.config_json`.
- **Code Version:** Git commit hash of the training repository stored in `jobs.code_version` (captured at config upload time).
- **Interface Version:** A version string for the `train()` function contract and `StructuredLogger` behavior, stored in `jobs.interface_version`.
- **Environment:** Placeholder for environment fingerprint (e.g., hash of `requirements.txt` or `uv.lock`), to be added to `jobs` metadata. For V1, manual tracking.
- **Deterministic Execution:** While not strictly enforced by the manager, users are encouraged to ensure their `train()` function is deterministic given the same config and seed.
## 7. Secrets Management
- **Supabase Credentials** (URL, anon key, service role key):
    - Stored as environment variables on the system where `sbatch` is run.
    - The `sbatch` script exports these variables, making them available to the `SLURM Manager`.
    - The `SLURM Manager` passes necessary credentials to `Worker Processes` (e.g., via environment or by injecting into `cfg` if absolutely necessary and secure).
- **FastAPI Admin API Key:** Stored as an environment variable for the FastAPI server process.
## 8. Development & Implementation Plan

## Implementation Status
The following core pieces are implemented and covered by tests:
 - `SupabaseMockClient` and reset utility
 - Mock trainer used for local runs
 - Configuration upload script
 - Full `StructuredLogger`
 - Worker process script
 - FastAPI backend with job, config, metrics, kill, and requeue endpoints
 - SLURM manager with worker spawning, heartbeat monitoring, idle timeout, and signal handling

Remaining components:
- **Real Supabase Integration:** Transition all components from mock to real Supabase.
- **SLURM `sbatch` Script:** Develop and test.
- **End-to-End Testing:** Full flow on a SLURM cluster with a simple real training script.
- **`FastAPI Backend` (Full):** Caching, WebSocket considerations (if pursued for V1).

## 9. Future Considerations (Post-V1)
- Advanced UI features (config diffing, detailed plot customization).
- Automated environment fingerprinting for reproducibility.
- More sophisticated job scheduling or prioritization within the manager.
- Dynamic scaling of workers.
- Broader error recovery patterns (e.g., more granular resume).
- Enhanced security (RBAC for UI/API).
- Rate limiting for API endpoints.
- Direct WebSocket metric streaming from workers to FastAPI.

