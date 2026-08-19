"""Fixtures for tests that need a real PostgreSQL database.

The suite refuses any database whose name does not end in ``_test`` and
destructively recreates its schemas between tests, mirroring dr-platform's own
convention.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

from dr_exp.config.machine import MachineProfile

DATABASE_URL_ENV = "DR_EXP_TEST_DATABASE_URL"
DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg:///dr_exp_test"


def test_database_url() -> str:
    """The database this suite is allowed to destroy."""
    url = os.environ.get(DATABASE_URL_ENV, DEFAULT_TEST_DATABASE_URL)
    name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not name.endswith("_test"):
        raise RuntimeError(
            f"{DATABASE_URL_ENV} must name a database ending in '_test', got {name!r}"
        )
    return url


def reset_database(engine: Engine) -> None:
    """Drop every schema this stack creates, leaving an empty database."""
    with engine.begin() as connection:
        for schema in ("dbos", "public"):
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        connection.execute(text('CREATE SCHEMA "public"'))


@pytest.fixture(scope="session")
def database_url() -> str:
    return test_database_url()


@pytest.fixture
def clean_database(database_url: str) -> Iterator[str]:
    engine = create_engine(database_url)
    try:
        reset_database(engine)
    finally:
        engine.dispose()
    return database_url


@pytest.fixture
def profile(tmp_path: Path, clean_database: str) -> MachineProfile:
    """A CPU machine profile pointing at the disposable test database."""
    return MachineProfile.model_validate(
        {
            "name": "pytest",
            "accelerator": "cpu",
            "python_executable": sys.executable,
            "workspace_root": tmp_path / "workspace",
            "run_store_root": tmp_path / "runs",
            "database_url": clean_database,
            "system_database_url": clean_database,
            "executor_id": "pytest-0",
            "worker_concurrency": 2,
        }
    )


@pytest.fixture
def engine(profile: MachineProfile) -> Iterator[Engine]:
    from dr_exp.platform.database import build_engine, initialize_schema

    initialize_schema(profile)
    created = build_engine(profile)
    try:
        yield created
    finally:
        created.dispose()
