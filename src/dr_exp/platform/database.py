"""Database access shared by the CLI, the worker, and the dispatcher."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from dr_platform import upgrade_platform_schema
from sqlalchemy import Engine, create_engine

from dr_exp.config.machine import MachineProfile


def build_engine(profile: MachineProfile) -> Engine:
    """Open a SQLAlchemy engine against the platform database."""
    return create_engine(profile.database_url)


@contextmanager
def engine_for(profile: MachineProfile) -> Iterator[Engine]:
    """Yield an engine and dispose it when the caller is done."""
    engine = build_engine(profile)
    try:
        yield engine
    finally:
        engine.dispose()


def initialize_schema(profile: MachineProfile) -> None:
    """Install the dr-platform ledger and dr-store tables.

    Idempotent: Alembic upgrades to head and does nothing when already there.
    """
    upgrade_platform_schema(profile.database_url)


__all__ = ["build_engine", "engine_for", "initialize_schema"]
