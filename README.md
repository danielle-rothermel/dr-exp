# dr-exp

A durable experiment manager for machine-learning training runs. dr-exp is a
thin layer over two packages that do the hard parts:

- **[dr-platform](https://github.com/danielle-rothermel/dr-platform)** owns the
  durable queue and ledger on PostgreSQL + DBOS: submission, admission with
  capacity and pause controls, label-routed queues, priority, cancellation that
  reaches running work, retry, and inspection.
- **[dr-exec](https://github.com/danielle-rothermel/dr-exec)** runs one training
  attempt as an isolated child process with typed contracts: a working-directory
  grant, an environment grant, budgets, cancellation, and a durable run record.

dr-exp supplies the experiment-shaped parts: a YAML configuration model, sweep
expansion, content-addressed job identity, machine profiles, a one-stage
training pipeline, and a CLI.

## Quick start

```bash
uv sync --all-groups
createdb dr_exp_dev

uv run dr_exp init --machine mini
uv run dr_exp sweep --machine mini --run demo configs/examples/dummy_sweep.yaml
uv run dr_exp worker --machine mini --with-dispatcher --max-jobs 2
uv run dr_exp list --machine mini
```

## Machine profiles

Every host-specific value lives in a machine profile under `configs/machines/`,
and every command takes `--machine`. Nothing else in dr-exp hardcodes a path,
a database, or an interpreter.

| Field | Meaning |
| --- | --- |
| `name` | Profile identity, for logs and messages. |
| `accelerator` | `cpu`, `mps`, or `cuda`. Selects the queue this worker drains. |
| `python_executable` | Absolute interpreter that runs training children. |
| `workspace_root` | Root for stored configs and per-attempt workspaces. |
| `run_store_root` | Root for dr-exec's durable run records. |
| `database_url` | Platform database. |
| `system_database_url` | DBOS system database. Must be the same database. |
| `executor_id` | This process's DBOS identity. One live process per id. |
| `worker_concurrency` | Attempts this worker runs at once. |
| `device_env` | Env templates rendered per device, e.g. `{"CUDA_VISIBLE_DEVICES": "{device}"}`. |
| `termination_grace_seconds` | SIGTERM-to-SIGKILL window for a child. Default 30. |
| `sweep_executor_ids` | Optional static set of live executors for the sweep. |

`mini.yaml` is the local Mac profile and is exercised by the smoke run.
`torch.yaml` declares the shape of a SLURM/CUDA profile but contains
placeholders: cluster bootstrap is a later phase and no dr-exp code runs
against it yet.

The platform tables and the DBOS system schema must share one PostgreSQL
database; dr-platform validates that and refuses to start otherwise.

## Job configuration

A job is one YAML document parsed into a validated model.

```yaml
entry_point: dr_exp.training.dummy_trainer:train
params:
  epochs: 3
labels:
  accelerator: cpu
priority: 100
budgets:
  wall_time_seconds: 300
tags:
  - example
```

`labels` must declare an `accelerator`; it is what routes the work to a queue.
`entry_point` is checked for importability at submission time, in one place.

A sweep is a base job plus a grid, expanded as a Cartesian product. Grid axes
override `params` by key.

```yaml
base:
  entry_point: dr_exp.training.dummy_trainer:train
  params: {epochs: 2}
  labels: {accelerator: cpu}
grid:
  learning_rate: [0.01, 0.001]
```

### Identity and deduplication

A job's `work_key` is the digest of its resolved configuration excluding
`priority` and `tags`, so rescheduling or re-tagging a job does not create new
work, while changing what it computes does. Submitting an identical
configuration into the same campaign reuses the existing work item.

`execution_config_reference` records the pipeline and trainer-contract version
on every run. Both digests are persisted identity and are pinned by golden
tests in `tests/unit/test_identity.py`.

## The trainer contract

A trainer is one module-level synchronous callable, addressed as
`package.module:function`:

```python
def train(request: dict) -> dict: ...
```

- **Input** is strict JSON with four keys: `params` (the config's params),
  `workspace` (an absolute directory that already exists), `work_key`, and
  `attempt`.
- **Output** must be strict JSON: no dataclasses, `datetime`, `Path`, NumPy
  scalars, or non-finite floats. dr-exp writes it to `result.json` in the
  workspace.
- **Artifacts** belong under `request["workspace"]`, which is also the child's
  working directory and survives the run.
- **SIGTERM means checkpoint and exit.** Cancellation and worker shutdown send
  SIGTERM, then SIGKILL after `termination_grace_seconds`. A trainer that wants
  to resume should checkpoint within that window.
- **At-least-once.** A stage body can run again after recovery, so a trainer
  should tolerate re-execution of the same `work_key`.

The entry point must be importable by the profile's `python_executable`.
dr-exec runs the child in isolated mode (`python -I`), so `PYTHONPATH` is
ignored: the trainer's package must actually be installed in that interpreter's
environment.

`dr_exp.training.dummy_trainer` implements this contract and is what the tests
and smoke run use.

## Queues, capacity, and priority

There is one pipeline, `dr-exp-train` v1, with one stage, `train`. Work routes
to a queue by its accelerator label:

| `accelerator` | queue |
| --- | --- |
| `cpu` | `train-cpu` (also the stage default) |
| `mps` | `train-mps` |
| `cuda` | `train-cuda` |

Every worker drains `train-cpu` plus its own accelerator's queue, so CPU work
runs anywhere while accelerator work stays on matching hardware.

Admission never runs a stage that has no capacity control, so a worker's
startup sets the stage default and its own accelerator's capacity to its
`worker_concurrency` if they are not already set. After that, capacity is an
operator decision and startup leaves it alone. Change it with
`dr_exp capacity`, and stop or restart admission with `dr_exp pause` and
`dr_exp resume`; neither preempts work that is already running.

### Priority direction

**Lower numbers run sooner, and 0 is the highest priority.** This is
dr-platform's convention and dr-exp keeps it. Configurations default to a
baseline of **100**, which leaves room to move a job ahead of everything
already queued:

```bash
dr_exp boost --machine mini --priority 5 <work-key>
```

## Commands

```bash
dr_exp init      --machine mini
dr_exp submit    --machine mini --run <run> [--campaign C] [--priority N] <config.yaml>
dr_exp sweep     --machine mini --run <run> [--campaign C] [--dry-run] <spec.yaml>
dr_exp list      --machine mini [--campaign C]
dr_exp status    --machine mini [--campaign C] [--run <run>]
dr_exp show      --machine mini [--campaign C] <work-key>
dr_exp cancel    --machine mini [--campaign C] <work-key>
dr_exp boost     --machine mini [--campaign C] --priority N <work-key>
dr_exp retry     --machine mini [--campaign C] <work-key>
dr_exp pause     --machine mini [--accelerator A]
dr_exp resume    --machine mini [--accelerator A]
dr_exp capacity  --machine mini [--accelerator A] [--capacity N]
dr_exp worker    --machine mini [--with-dispatcher] [--max-jobs N] [--deadline-seconds S]
dr_exp dispatcher --machine mini [--deadline-seconds S]
```

Work keys accept a unique prefix. `--max-jobs` makes a worker exit once that
many work items in the campaign are terminal, which is what the smoke run uses;
without it a worker runs until SIGTERM or SIGINT, then drains its in-flight
attempts and exits.

`--with-dispatcher` runs admission, the run barrier, and the abandoned-work
sweep in the same process, which is the normal single-machine setup. With
several workers, run the dispatcher in exactly one of them, or give that one
every live executor id through `sweep_executor_ids`, so peer work is not
mistaken for abandoned.

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

Integration tests need a disposable PostgreSQL database. They default to
`postgresql+psycopg:///dr_exp_test` and refuse any database whose name does not
end in `_test`, because they recreate its schemas between tests. Override with
`DR_EXP_TEST_DATABASE_URL`.

```bash
createdb dr_exp_test
uv run pytest -q -m "not integration"   # unit tests only
```

See [CHANGELOG.md](CHANGELOG.md) for release history.
