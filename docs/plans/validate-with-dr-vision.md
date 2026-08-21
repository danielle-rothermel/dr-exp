# Plan: validate dr-exp with dr-vision's warm-start experiments

Status: planned, 2026-08-21. Depends on dr-vision reaching milestone M2 of
`dr-vision/docs/plans/warm-start-reimplementation.md` (the `train(request)`
entry point with checkpoint/resume). Machine: `mini`.

## Goal

Use a real training workload — dr-vision's re-implementation of Ash & Adams'
warm-starting experiments — to validate dr-exp end to end on the `mini`
profile, and to run the first experiments that validate the warm-start
implementation itself. The dummy trainer proves the plumbing; this proves the
product: hours-long MPS jobs, real checkpoints, real cancellation, real
concurrency, and a sweep whose results must come out in a known order.

## How dr-vision becomes a local dependency

Two constraints decide the shape:

1. **Dependency direction stays clean.** dr-exp never lists a research package
   as a runtime dependency, and dr-vision never depends on dr-exp (its trainer
   contract is plain JSON). Neither `pyproject.toml` `[project.dependencies]`
   changes.
2. **One interpreter.** dr-exec runs trainer children under `python -I`, so the
   trainer package and `dr_exp` must both be importable from the profile's
   `python_executable`. The `mini` profile already points at dr-exp's own
   venv (`~/drotherm/repos/dr-exp/.venv/bin/python`).

So dr-vision is installed **editable, from the sibling checkout, into dr-exp's
venv, through a dev-only dependency group**:

```toml
# pyproject.toml
[dependency-groups]
vision = ["dr-vision"]

[tool.uv.sources]
dr-vision = { path = "../dr-vision", editable = true }
```

- `uv sync --group vision` installs it (pulls torch/torchvision via dr-vision's
  own dependencies); a sync without the group installs neither. The
  `[tool.uv.sources]` entry is resolved by every uv command, though, so
  `../dr-vision` must exist for any `uv lock`/`uv sync`/`uv run` here.
- Editable means a dr-vision edit is live on the next job without reinstalling,
  which is what we want while both repos move.
- The group is documented as machine-local tooling: it assumes `../dr-vision`
  exists. CI does not resolve it; the lock entry is path-based.
- When dr-vision publishes to PyPI, the group switches to a pinned release and
  the `[tool.uv.sources]` entry is removed. Until then this is deliberately a
  local path.

Nothing in `src/dr_exp` references dr-vision. Jobs name the trainer through
`entry_point: dr_vision.entry:train` in their YAML, exactly as the dummy
trainer does.

## Preconditions (one-time, on `mini`)

- `git reset --hard origin/main && uv sync --group vision` in
  `~/drotherm/repos/dr-exp` (the committed `mini` profile depends on that venv
  holding both packages).
- Database `dr_exp_dev` exists (`createdb -h 127.0.0.1 dr_exp_dev`) and
  `dr_exp init --machine mini` has run (`--machine` is a subcommand option,
  not a top-level one).
- CIFAR-10 downloaded once into the data root dr-vision's params point at, so
  the first concurrent jobs do not race the download.
- `dr_exp --log-level INFO <subcommand> --machine mini` output captured to a
  file per session; sweep summaries and `identity_unavailable` must be visible.

## What gets validated, and how

Each run below is a dr-exp campaign of its own so ledgers never mix. Every
check is a state assertion read from the ledger (`dr_exp status` / `show`),
the workspace (`metrics.jsonl`, `rounds.json`, checkpoints), or dr-exec run
records — never a timing.

### V1 — single real job

One dr-vision job (CIFAR-10, ResNet-18, MPS, two-phase `n_samples=0.5`,
random init) via `dr_exp submit`, one worker with `--with-dispatcher`.

Validates: `python -I` import of `dr_vision` from the profile interpreter; the
workspace grant (checkpoints and `metrics.jsonl` survive the run); strict-JSON
return → `result.json`; a multi-hour attempt under the 50 ms engine poll and
the unbudgeted/finite `wall_time`; the run record in the run store; SUCCEEDED
in the ledger with the expected `output_reference`.

### V2 — the canary sweep (validates warm-start, exercises dr-exp)

dr-vision's three-job canary (random `(0,1)`, warm `(1,0)`, shrink-perturb
`(0.4,0.1)`; one seed) as one `dr_exp sweep`, `worker_concurrency` per the
throughput study (2 until it says otherwise).

Warm-start validation (dr-vision's acceptance): holdout accuracy ordering
`A ≈ C > B` with a multi-point gap; round-2 epochs-to-99% `B < C < A`.

dr-exp validation: three distinct `work_key`s from one sweep; all three route
to `train-mps`; admission respects capacity; two run concurrently while the
third waits READY and is admitted on the first completion; the dispatcher's
sweep line reports `identity_unavailable=False` throughout; no attempt is
projected `stale_app_version` or `dead_executor` during a multi-hour run.

### V3 — cancellation and resume on a real job

Submit the canary's random-init job again in a fresh campaign; after round 1
has written its first checkpoint, `dr_exp cancel` it.

Validates: SIGTERM reaches the child, dr-vision checkpoints within the 30 s
grace, the child PID is gone, ledger CANCELLED with `producer=cancellation` (no
FAILED attempt).

Then the resume half. Cancellation is terminal in dr-platform's ledger, so
`dr_exp retry` is *not* the path back: it prints that cancellation is permanent
and exits 1. The path is to resubmit the same config into a **new campaign**,
which creates a new work item (dedupe is per campaign and work key, so the old
campaign would resolve to the cancelled item). Workspaces are per
`(campaign_key, work_key)`, so the new campaign starts empty: copy the
cancelled item's workspace into the new campaign's before starting a worker.
That new work item's attempt 1 then **resumes from the checkpoint** — its
`result.json` carries a non-null `resumed_from` matching the checkpoint's
round/epoch, `metrics.jsonl` continues from there rather than restarting, and
it finishes SUCCEEDED. This is the at-least-once contract exercised for real.

### V4 — worker shutdown and recovery

With two jobs in flight, send SIGTERM to the worker process.

Validates: both children are torn down within grace (registry cancel + join);
work items remain `admitted`/PENDING, not terminal; a restarted worker with the
same `executor_id` and app version recovers them (DBOS recovery, within
`max_recovery_attempts`), and each resumes from its checkpoint.

### V5 — priority and dedupe

Submit the canary again into the V2 campaign: all three deduplicate to the
existing work (same `work_key`, no new attempts). Submit a fourth
configuration at priority 10 while two jobs are running: it is admitted ahead
of any READY item with priority 100 on the next free slot, and
`dbos.workflow_status.priority` reflects the boost after `dr_exp boost`.

### V6 — first batch-online run

One `n_samples=1000` shrink-perturb job (the long shape). Validates the
long-running path: many rounds, growing checkpoints under the latest-only
policy, per-round records, and a multi-hour attempt with no reconciliation
noise.

## What this is not

- Not part of `pytest -q`. These are runbook validations on the real machine;
  they take hours and need MPS. If any step is later automated, it lives
  behind an opt-in marker and never in CI.
- Not a reproduction of the paper. The paper-scale grids come after V1–V6 pass
  and after the throughput study sets concurrency; they are dr-vision's M3.

## Outputs

- A dated runbook record per validation (`docs/validation/YYYY-MM-DD-mini-*.md`
  in this repository) listing campaign keys, `work_key`s, the ledger states and
  record paths that were checked, and any dr-exp defect found.
- Defects found go to issues/PRs on the owning repository (dr-exp, dr-exec,
  dr-platform, or dr-vision). The runbook record links them.
- Throughput numbers from V2 and V6 feed `dr-vision/docs/infra/mini-throughput.md`.

## Order of operations

1. dr-vision M1 + M2 land (package, entry point, checkpoint/resume).
2. This repository: add the `vision` group and `[tool.uv.sources]` entry; sync.
3. V1 → V2 → V3 → V4 → V5 → V6, each in its own campaign, recording as above.
4. Fold throughput findings into the `mini` profile; start dr-vision M3.
