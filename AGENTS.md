# AGENTS.md: Quick Guide for Agentic Development (dr_exp)

## 1. Purpose
This guide directs agentic coders in developing the Experiment Manager (`dr_exp`). For full details, always refer to `docs/prd_v2.md` and component-specific spec files in `docs/`.

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

## 4. Phase 1 Task Breakdown: Mocks, Scaffolding & Core Local Components

**Always consult `docs/prd_v2.md` (especially Section 8.1 for Phase 1 details) and the specific `docs/<component_name>.md` for detailed task requirements, inputs, outputs, and expected behaviors.**

### Phase 1 Tasks (Highest Priority):
* **`Supabase Mock Client` & `Mock Reset Utility`**
    * **Objective:** Implement `SupabaseMockClient` (Python class) to simulate Supabase DB and Storage operations using local files/directories. Create `reset_mock_db.py` script to clear this mock environment.
    * **Primary Spec Doc:** `docs/supabase_mock.md`.
    * **Output:** `supabase_mock_client.py`, `reset_mock_db.py`.
    * **Context:** This client is crucial for offline development of other components (Worker, Config Generator). It should mimic the interface the real Supabase client will eventually have. The reset utility ensures repeatable test conditions.

* **`Mock Trainer`**
    * **Objective:** Implement a mock `train(cfg, logger)` function (Python) that simulates a training run, logs mock metrics, and saves mock artifacts/checkpoints using the `StructuredLogger` interface.
    * **Primary Spec Doc:** `docs/train_mock.md`.
    * **Output:** Python module with the mock `train` function.
    * **Context:** Enables testing of the `Worker Process` and `StructuredLogger` without needing actual model training. Must adhere to the defined training interface contract (see PRD Section 5).

* **`StructuredLogger` (Initial)**
    * **Objective:** Implement the initial version of the `StructuredLogger` class (Python) focusing on writing metrics, checkpoints, and artifacts to unique local paths provided via configuration.
    * **Primary Spec Doc:** `docs/logger.md`.
    * **Output:** `structured_logger.py`.
    * **Context:** This component is used by the `Mock Trainer` (and later the real `train()` function) to manage all local output. It does *not* upload to Supabase directly.

* **`Config Generator` (Initial)**
    * **Objective:** Implement the core logic of `upload_configs.py` (Python CLI script) to generate Hydra configurations and use the `SupabaseMockClient` (e.g., its `add_job` method) to simulate uploading/storing these configurations and creating corresponding job entries.
    * **Primary Spec Doc:** `docs/config_upload.md`.
    * **Output:** `upload_configs.py` script.
    * **Context:** This script is the entry point for defining experiments. Its initial version validates the config generation process and interaction with the (mock) job store.

* **`Basic Tests`**
    * **Objective:** Create `pytest` unit tests for each of the components developed in Phase 1.
    * **Input:** The implemented Python code for each component and its specification document.
    * **Output:** Test files (e.g., `tests/mock/test_supabase_mock_client.py`, `tests/test_logger.py`, `tests/test_mock_trainer.py`).
    * **Context:** Essential for verifying correctness and enabling refactoring. Tests should cover core functionalities, expected outputs, and basic error handling.

## 4. Simplified Agent Workflow (for Phase 1 Tasks)
2.  **Understand Specs:** Thoroughly read the primary spec document for the component (e.g., `docs/supabase_mock.md`) and relevant sections of `docs/prd_v2.md`.
3.  **Code & Test:** Implement the component in Python. Write `pytest` unit tests covering its specified behavior.
4.  **Review & Iterate:** Submit code and tests for human review. Revise based on feedback.
5.  **Integrate (Locally):** Human developer ensures the component can be (or will be) integrated with other Phase 1 mock components.

