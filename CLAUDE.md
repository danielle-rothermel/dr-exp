# dr-exp

A durable experiment manager: a thin layer over **dr-platform** (durable
queue/ledger on PostgreSQL + DBOS) and **dr-exec** (one training attempt as an
isolated child process). dr-exp owns the config model, job identity, machine
profiles, the training pipeline, and the CLI. Read `README.md` first — it is the
user-facing contract and this file does not repeat it.

## Layout

```
src/dr_exp/
├── config/      names.py (closed vocabularies + persisted literals)
│                job.py (JobConfig, SweepSpec), identity.py (digests)
│                machine.py (MachineProfile)
├── execution/   attempt.py (dr-exec job construction and outcomes)
│                cancellation.py (signal fan-out), store.py (input references)
├── platform/    pipeline.py (the one pipeline and its stage body)
│                worker.py (DBOS runtime), submission.py, drain.py
│                inspection.py, database.py, registry.py, version.py
├── training/    dummy_trainer.py (the reference trainer)
└── cli/         main.py
```

## Invariants worth knowing before editing

**Persisted identity is pinned.** The literals in `config/names.py` and the
digest documents in `config/identity.py` are stored in the ledger. Golden tests
in `tests/unit/test_identity.py` pin them verbatim. A failure there means
"confirm this re-identification is intended", never "update the expected value".

**Worker registration order is load-bearing.** `platform/worker.py` documents
it: dr-platform requires wrapped workflows, queues, and the dispatcher to be
registered before `DBOS.launch()`. DBOS identity is separate and comes from
config — `build_platform_dbos_config`'s `application_version` and `executor_id`
fields pin this process, using a version derived in `platform/version.py`.
dr-exp pins an explicit version rather than letting DBOS hash workflow source,
so the version is stable across local edits; the sweep fails live attempts
carrying any other version as `stale_app_version`.

**Stage bodies are preemptible.** The `train` body in `platform/pipeline.py`
runs inside a preemptible DBOS step: no DBOS steps or transactions inside it,
re-raise `asyncio.CancelledError`, keep the return small, and tolerate
at-least-once execution.

**One live process per executor id.** Dead-executor detection reads executor
identity, so two processes sharing an id make the sweep lie.

**Register the wrapped pipeline.** `build_registry` wraps before registering;
`register_scheduled_dispatcher` rejects an unwrapped one. The deliberately
unwrapped `platform/registry.py` registry is for submission and inspection only.

**A JobId is single-use.** dr-exec derives its run-record directory from the
job id, so every attempt mints a fresh one.

**Children run isolated.** dr-exec launches with `python -I`, so `PYTHONPATH`
does not reach the child; a trainer's package must be installed in the
profile's interpreter.

**DBOS's registry is process-global.** `worker_runtime` tears down with
`DBOS.destroy(destroy_registry=True)` so a second runtime in one process can
redeclare its queues and workflows. Tests depend on this.

## Conventions

- Boundary and parsed types are pydantic `BaseModel`; internal value objects are
  frozen slotted dataclasses.
- Closed string sets are `StrEnum` with `@verify(UNIQUE)`; persisted-format
  literals get a named owner plus a golden test.
- Tests synchronize on state, never on elapsed time. Time appears only as a
  watchdog, where reaching it is a failure.
- Use `uv add` / `uv remove`, never `pip install`.

## Gates

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

Integration tests need `createdb dr_exp_test` and run in one process (DBOS
registers a process-global dispatcher, so no `-n auto`).
