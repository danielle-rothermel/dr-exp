"""Durable storage for the submitted ``JobConfig`` behind an input reference.

dr-platform treats ``input_reference`` as an opaque string. dr-exp stores the
resolved configuration as a content-addressed object in dr-store on the
platform database, so a worker resolves it without a shared filesystem. The
enlisted ObjectStore API is the Postgres path; ``BlockingObjectStore`` is a
SQLite event-loop facade and is not used here.
"""

from __future__ import annotations

from typing import cast

from dr_serialize import Jsonable
from dr_store import (
    ContentHashMismatchError,
    ObjectNotFoundError,
    ObjectReference,
    ObjectStore,
    PostgresBackend,
    ReferenceValidationError,
    SchemaMismatchError,
    format_object_reference,
    parse_object_reference,
)
from pydantic import ValidationError
from sqlalchemy import Engine

from dr_exp.config.job import ConfigError, JobConfig
from dr_exp.config.names import JOB_CONFIG_SCHEMA

_STORE_READ_ERRORS = (
    ObjectNotFoundError,
    ContentHashMismatchError,
    SchemaMismatchError,
)


def _unresolved_input_reference(reference: str, cause: BaseException) -> ConfigError:
    return ConfigError(f"input reference could not be resolved: {reference}: {cause}")


def _job_config_document(config: JobConfig) -> Jsonable:
    return cast(Jsonable, config.model_dump(mode="json"))


def reference_for_job_config(config: JobConfig) -> str:
    """Return the content-addressed input reference without storing ``config``."""
    return format_object_reference(
        ObjectReference.for_record(JOB_CONFIG_SCHEMA, _job_config_document(config))
    )


def parse_job_config_reference(reference: str) -> ObjectReference:
    """Parse an input reference and require the pinned job-config schema."""
    try:
        parsed = parse_object_reference(reference)
    except ReferenceValidationError as error:
        raise ConfigError(
            f"input reference is not a dr-store object: {reference}: {error}"
        ) from error
    if parsed.schema != JOB_CONFIG_SCHEMA:
        raise ConfigError(
            f"input reference schema is not {JOB_CONFIG_SCHEMA}: {parsed.schema}"
        )
    return parsed


def job_config_from_document(document: object, *, reference: str) -> JobConfig:
    """Validate a fetched object-store record into a ``JobConfig``."""
    try:
        return JobConfig.model_validate(document)
    except ValidationError as error:
        raise ConfigError(
            f"input reference is not a valid JobConfig: {reference}: {error}"
        ) from error


def store_job_config(config: JobConfig, *, engine: Engine) -> str:
    """Persist ``config`` and return its opaque input reference.

    Writing is idempotent: identical canonical JSON yields the same
    content-addressed reference.
    """
    store = ObjectStore(PostgresBackend.open_sync(engine))
    with engine.begin() as connection:
        reference, _ = store.put_enlisted(
            connection,
            JOB_CONFIG_SCHEMA,
            _job_config_document(config),
        )
    return format_object_reference(reference)


def load_job_config_reference(reference: str, *, engine: Engine) -> JobConfig:
    """Resolve an input reference written by :func:`store_job_config`."""
    parsed = parse_job_config_reference(reference)
    store = ObjectStore(PostgresBackend.open_sync(engine))
    with engine.connect() as connection:
        try:
            document = store.get_enlisted(connection, parsed)
        except _STORE_READ_ERRORS as error:
            raise _unresolved_input_reference(reference, error) from error
    return job_config_from_document(document, reference=reference)


__all__ = [
    "job_config_from_document",
    "load_job_config_reference",
    "parse_job_config_reference",
    "reference_for_job_config",
    "store_job_config",
]
