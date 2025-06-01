# Experiment Manager (dr_exp)
## 1. Overview
- The Experiment Manager (`dr_exp`) is a system designed to coordinate, execute, monitor, and track large-scale deep learning experiments, primarily on SLURM-managed GPU clusters. It aims to streamline the experimentation lifecycle by providing tools for efficient configuration management, robust job execution, centralized data collection (configurations, metadata, logs, metrics, artifacts), and real-time monitoring via a web interface.
- This system prioritizes reproducibility, modularity for agent-ready development, and researcher-centric control.
## 2. Key Features
- **Efficient Experimentation:** Simplified definition and execution of hyperparameter sweeps using Hydra.
- **Robust Job Execution:** Designed for SLURM environments, with considerations for error handling and job management.
- **Centralized** Data** Management:** Uses Supabase (PostgreSQL and Object Storage) as a single source of truth for all experiment-related data.
- **Real-time Monitoring & Control:** A React-based web UI (Babysitter UI) provides live insights and control over experiments via a FastAPI backend.
- **Reproducibility:** Captures code versions, configurations, and (planned) environment details.
- **Modular & Agent-Ready Design:** Components are designed with clear interfaces for independent development and testing, suitable for agentic coders.
## 3. System Architecture
- The system comprises several key components that interact to manage the experiment lifecycle:
- ```plain text
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
- For a detailed breakdown, please refer to the Product Requirements Document (PRD - `docs/product_requirement_doc.md`).
### Core Components:
- **Config Generator (CLI):** Generates and uploads Hydra-based experiment configurations to Supabase.
- **Supabase:** Central PostgreSQL database and object storage.
- **SLURM Manager:** Python script launched by SLURM `sbatch`; manages worker processes on allocated nodes/GPUs.
- **Worker Process:** Python script that claims jobs, runs training logic, logs metrics/artifacts using `StructuredLogger`, and uploads results.
- **StructuredLogger:** Python class used by training code to handle local logging of metrics, checkpoints, and artifacts.
- **FastAPI Backend:** Serves as the API layer between Supabase and the UI/other clients.
- **React Babysitter UI:** Web interface for monitoring and controlling experiments.
- **Mock Components:** Local mocks for Supabase, FastAPI, and the training function to facilitate offline development and testing.
## 4. Getting Started
### 4.1. Prerequisites
- Python (e.g., 3.9+)
- Node.js and npm (for Supabase CLI, if not using other installation methods like Homebrew)
- Docker (for running Supabase locally via `supabase start` during development)
- A Supabase Account (for the remote cloud instance)
- [Supabase CLI](https://supabase.com/docs/guides/cli/getting-started) installed and configured.
- Git
### 4.2. Repository Setup
**Project Structure (Overview):**
```plain text
dr_exp/
├── dr_exp/              # Main Python package
│   ├── mock/            # Mock components (e.g., supabase_mock_client.py)
│   ├── core/            # Core logic (to be developed)
│   └── ...
├── supabase/            # Supabase project configuration and migrations
│   ├── config.toml
│   └── migrations/
│       └── 0001_initial_schema.sql
├── react-babysitter-ui/ # React frontend
├── scripts/             # Utility scripts (e.g., reset_mock_db.py)
├── tests/               # Pytest tests
├── docs/                # Project documentation (PRD, specs)
├── mock_db/             # Local mock database files (in .gitignore)
├── mock_storage/        # Local mock storage files (in .gitignore)
├── .gitignore
└── README.md
```
### 4.3. Environment Setup

Python Backend
```
uv sync
uv run python scripts/start_backend.py
```

Frontend
```
cd react-babysitter-ui
npm install
npm run dev
```

### 4.4. Configuration
- The system will rely on environment variables for sensitive information like Supabase keys. Create a `.env` file (and add it to `.gitignore`) for local development. Example:
```plain text
# .env - For local development (DO NOT COMMIT if it contains real secrets)
# Supabase connection details for the REAL client (not the mock)
SUPABASE_URL="your_supabase_project_url"
SUPABASE_KEY="your_supabase_anon_key"
SUPABASE_SERVICE_ROLE_KEY="your_supabase_service_role_key"

# Mode for client selection (mock or real)
EXPMGR_MODE="mock" # Set to "real" to use actual Supabase
```
- Your application code will need to load these (e.g., using `python-dotenv`).

## 6. Development
### 6.1. Mocks
- **SupabaseMockClient:** Simulates Supabase interactions locally. See `dr_exp/mock/supabase_mock_client.py`.
- Other mocks, including the FastAPI backend and mock training function, are implemented as described in the PRD.
### 6.2. Testing
- Tests are written using pytest and located in the tests/ directory.
- To run tests:
```plain text
uv run pytest
```
## 7. Documentation
- **Product Requirements Document (PRD):** `docs/product_requirement_doc.md`
- **Component Specifications:** Detailed design documents for each component are located in the `docs/` directory (e.g., `docs/supabase_schema.md`, `docs/worker.md`).
- This README provides a starting point. It should be updated as the project evolves, particularly the "Getting Started" and "Running the System" sections.

