# Changelog

## Unreleased — Phase 3: rebuild on dr-platform and dr-exec

Replaced the filesystem job queue, in-process worker, worker launcher, SLURM
CLI, and Hydra configuration with a durable stack:

- **Queue and ledger** are now dr-platform 0.2.2 on PostgreSQL + DBOS, giving
  durable submission, admission with capacity and pause controls, label-routed
  queues, priority, cancellation that reaches running work, retry, and
  reconciliation of abandoned work.
- **Execution** is now dr-exec 0.1.11: each attempt is an isolated child
  process with an explicit working-directory grant, environment grant, budgets,
  cancellation, and a durable run record.
- **Configuration** is pydantic models parsed from YAML, replacing Hydra and
  OmegaConf. Sweeps expand a base job across a Cartesian grid.
- **Job identity** is content-addressed: `work_key` digests the resolved
  configuration excluding priority and tags, so identical work deduplicates.
- **Machine profiles** ship inside the `dr_exp` package (`dr_exp.config.machines`)
  and own every host-specific value. `mini` is the local Mac profile; `torch`
  declares a SLURM/CUDA profile as placeholder data.
- **Trainer contract** is `def train(request: dict) -> dict`, strict JSON in and
  out, artifacts under `request["workspace"]`, SIGTERM meaning checkpoint and
  exit.
- **CLI** gained `init`, `sweep`, `status`, `show`, `cancel`, `boost`, `retry`,
  `pause`, `resume`, `capacity`, `worker`, and `dispatcher`; the `slurm`
  command group and the Hydra-based `submit`/`sweep` were removed.

Removed `hydra-core` and `omegaconf`; added `dr-exec`, `dr-platform`,
`dr-serialize`, `psycopg[binary]`, and `sqlalchemy`.

Known limits of this phase: only the single-worker local setup is exercised
(one live process per `executor_id`), and upgrading dr-exp, dr-platform,
dr-exec, or dbos changes the pinned DBOS application version, so work still
PENDING from the previous version is failed by the sweep as
`stale_app_version`.

Priority direction is dr-platform's: lower numbers run sooner and 0 is highest.
dr-exp submits at a baseline of 100 so `dr_exp boost` can move work ahead.

## 2026-08-18 — Phase 1 strip

Removed Supabase sync, FastAPI remote API, React UI, sync queue, obsolete
scripts and implementation-guide docs. Excised sync coupling from JobDB,
Worker, and CLI. Consolidated on `dr_exp.training.dummy_trainer.train` for
tests and smoke runs. Pruned runtime dependencies; dev tooling lives in
dependency groups only.
