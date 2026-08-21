"""Content-addressed job-config input references."""

from __future__ import annotations

import pytest
from dr_store import (
    MemoryBackend,
    OBJECT_REFERENCE_PREFIX,
    ObjectNotFoundError,
    ObjectReference,
    ObjectStore,
    PutStatus,
    format_object_reference,
)

from dr_exp.config.job import ConfigError, JobConfig
from dr_exp.config.names import JOB_CONFIG_SCHEMA
from dr_exp.execution import store as store_module
from dr_exp.execution.store import (
    job_config_from_document,
    parse_job_config_reference,
    reference_for_job_config,
)

CONFIG = JobConfig(
    entry_point="dr_exp.training.dummy_trainer:train",
    params={"epochs": 2},
    labels={"accelerator": "cpu"},
)


def test_identical_configs_yield_identical_references() -> None:
    copied = CONFIG.model_copy()
    assert reference_for_job_config(copied) == reference_for_job_config(CONFIG)


def test_reference_uses_the_pinned_schema_and_prefix() -> None:
    reference = reference_for_job_config(CONFIG)
    assert reference.startswith(f"{OBJECT_REFERENCE_PREFIX}:{JOB_CONFIG_SCHEMA}:")
    parsed = parse_job_config_reference(reference)
    assert parsed.schema == JOB_CONFIG_SCHEMA


def test_reference_changes_when_the_stored_document_changes() -> None:
    rescheduled = CONFIG.model_copy(update={"priority": 7})
    retargeted = CONFIG.model_copy(update={"params": {"epochs": 3}})
    assert reference_for_job_config(rescheduled) != reference_for_job_config(CONFIG)
    assert reference_for_job_config(retargeted) != reference_for_job_config(CONFIG)


@pytest.mark.parametrize(
    "reference",
    [
        "/workspace/configs/abc.json",
        "dr-store-object:v1:not-a-hash",
        f"{OBJECT_REFERENCE_PREFIX}:{JOB_CONFIG_SCHEMA}:zzzz",
        f"{OBJECT_REFERENCE_PREFIX}:{JOB_CONFIG_SCHEMA}:{'g' * 64}",
    ],
)
def test_malformed_reference_is_a_config_error(reference: str) -> None:
    with pytest.raises(ConfigError, match="not a dr-store object"):
        parse_job_config_reference(reference)


def test_unknown_schema_is_a_config_error() -> None:
    reference = format_object_reference(
        ObjectReference(schema="other.schema/v1", content_hash="a" * 64)
    )
    with pytest.raises(ConfigError, match="schema is not"):
        parse_job_config_reference(reference)


async def test_round_trip_put_get_is_identical_job_config() -> None:
    store = ObjectStore(MemoryBackend())
    document = CONFIG.model_dump(mode="json")
    stored, status = await store.put(JOB_CONFIG_SCHEMA, document)
    assert status is PutStatus.STORED
    loaded = await store.get(stored)
    reference = format_object_reference(stored)
    assert job_config_from_document(loaded, reference=reference) == CONFIG
    assert reference == reference_for_job_config(CONFIG)


async def test_second_put_of_the_same_config_is_idempotent() -> None:
    store = ObjectStore(MemoryBackend())
    document = CONFIG.model_dump(mode="json")
    first, _ = await store.put(JOB_CONFIG_SCHEMA, document)
    second, status = await store.put(JOB_CONFIG_SCHEMA, document)
    assert status is PutStatus.IDEMPOTENT
    assert second == first


async def test_missing_object_is_a_config_error() -> None:
    store = ObjectStore(MemoryBackend())
    reference = reference_for_job_config(CONFIG)
    parsed = parse_job_config_reference(reference)
    with pytest.raises(ObjectNotFoundError) as caught:
        await store.get(parsed)
    error = store_module._unresolved_input_reference(reference, caught.value)
    assert isinstance(error, ConfigError)
    assert "could not be resolved" in str(error)
    assert reference in str(error)


async def test_stored_non_job_config_is_a_config_error() -> None:
    store = ObjectStore(MemoryBackend())
    stored, _ = await store.put(JOB_CONFIG_SCHEMA, {"not": "a job config"})
    document = await store.get(stored)
    reference = format_object_reference(stored)
    with pytest.raises(ConfigError, match="not a valid JobConfig"):
        job_config_from_document(document, reference=reference)
