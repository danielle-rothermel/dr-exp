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

### 3.1 Frontend Checks

If you modify anything inside `react-babysitter-ui/`, ensure the React project still builds:

```
cd react-babysitter-ui
npm install
npm run dev
```
The Vite dev server should start without missing-module errors.

## 4. Simplified Agent Workflow (for Phase 1 Tasks)
2.  **Understand Specs:** Thoroughly read the primary spec document for the component (e.g., `docs/supabase_mock.md`) and relevant sections of `docs/product_requirement_doc.md`.
3.  **Code & Test:** Implement the component in Python. Write `pytest` unit tests covering its specified behavior.
4.  **Review & Iterate:** Submit code and tests for human review. Revise based on feedback.
5.  **Integrate (Locally):** Human developer ensures the component can be (or will be) integrated with other Phase 1 mock components.
