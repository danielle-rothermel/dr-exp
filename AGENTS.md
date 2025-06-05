# AGENTS.md: Quick Guide for Agentic Development (dr_exp)

## 1. Purpose
This guide directs agentic coders in developing the Experiment Manager (`dr_exp`).

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
