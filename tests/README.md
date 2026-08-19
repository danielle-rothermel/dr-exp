# dr_exp Test Suite

## Structure

```
tests/
├── unit/           # JobDB, worker, lifecycle
├── integration/    # CLI, sweeps, launcher, SLURM
├── validation/     # Project structure and docs
├── utils/          # Shared helpers
└── conftest.py     # Shared fixtures
```

## Running Tests

Install test dependencies first (`uv sync --group test` or `--all-groups`). Default `addopts` include `-n auto`, so **pytest-xdist must be installed** for a normal `uv run pytest` invocation.

```bash
uv sync --all-groups
uv run pytest                    # full suite (parallel via xdist)
uv run pytest -m "not slow"      # skip slow tests
uv run pytest tests/unit/        # unit only
uv run pytest -x                 # stop on first failure
uv run pytest -n0                # disable parallelism
```

## Conventions

- Use `temp_job_db` and `temp_experiment_dir` fixtures from `conftest.py`
- Use `create_test_config()` from `tests/utils/job_helpers.py` for job configs
- Default trainer target: `dr_exp.training.dummy_trainer.train`
- Prefer `@pytest.mark.integration` for multi-component tests
- Prefer `@pytest.mark.slow` for tests that sleep or poll for extended periods

## Markers

Defined in `pyproject.toml`:

- `slow` — long-running; deselect with `-m "not slow"`
- `integration` — cross-component workflows
- `unit` — isolated component tests
- `concurrency` — multi-worker / lock contention
- `gpu` — requires GPU hardware

## Parallel Execution

pytest-xdist runs with `-n auto` by default (see `pyproject.toml` addopts). If a test is flaky under parallelism, mark it `@pytest.mark.serial`.
