# Frontend Babysitter UI Specification (`docs/frontend_ui.md`)

## Purpose

The React-based Babysitter UI provides real-time visibility and control over experiment execution. It displays the status of all jobs, their associated metadata and metrics, allows user-initiated control actions (kill, requeue), and visualizes training logs and artifacts.

It is meant to support researchers in monitoring and debugging sweeps, triaging failures, and understanding optimization dynamics at scale.

---

## Responsibilities

* Display all jobs and their current status (`queued`, `running`, `completed`, etc.)
* Allow filtering and grouping by sweep, config, status, or error type
* Render live metric plots and scalar summaries (via FastAPI or `.jsonl`)
* Display logs, config, and artifact previews for each job
* Allow manual control actions (kill, requeue, delete)
* Indicate failures and retry lineage

---

## Major Views / Components

### 1. **Job Table View**

* Overview of all jobs with sortable columns (e.g., `status`, `start_time`, `val_acc`)
* Click-to-expand drawer showing full config and metadata
* Tag or label columns for grouping (e.g., sweep nickname)

### 2. **Job Detail Page**

* Live or cached metric plots (val loss, accuracy, divergence, etc.)
* Display `.jsonl` logs, training.log, error tracebacks
* Artifact browser (e.g., plots, config snapshots)
* Actions: requeue, kill, delete

### 3. **Sweep Overview Page** (Optional)

* Show sweep-level aggregates (e.g., best/worst job, metric histogram)
* Display number of jobs by status, error mode
* Link to underlying job views

---

## Backend Integration

The UI relies on the FastAPI backend to provide:

* Job metadata (`GET /job/{id}`)
* Config details (`GET /config/{id}`)
* Metric summaries (`GET /metrics/{id}`)
* WebSocket stream (`/ws/metrics/{id}`) or polling fallback
* Job control APIs (kill/requeue)

All backend endpoints must be secured appropriately (see `api_contracts.md`).

---

## Authentication

* Users log in using Supabase Auth (email/password or token)
* Admins can access control features (kill, requeue, delete)
* Viewer-only roles may browse but not modify job states

---

## Deployment Notes

* UI is deployed via Netlify, Vercel, or static server
* Uses Tailwind CSS and modular React components (or Vite)
* Auth token stored securely in local storage or browser session

---

