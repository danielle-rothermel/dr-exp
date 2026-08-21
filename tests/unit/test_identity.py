"""Golden tests pinning dr-exp's persisted identity formats.

These literals are stored in the dr-platform ledger. If a change to the config
model or the identity document alters them, every future submission stops
deduplicating against existing work and provenance references drift. A failure
here means "confirm this re-identification is intended", not "update the
expected value".
"""

from __future__ import annotations

import pytest

from dr_exp.config.identity import (
    execution_config_document,
    execution_config_reference,
    work_identity_document,
    work_key,
)
from dr_exp.config.job import Budgets, JobConfig
from dr_exp.config.names import (
    PIPELINE_KEY,
    PIPELINE_VERSION,
    STAGE_KEY,
    TRAINER_CONTRACT,
    JOB_CONFIG_SCHEMA,
    Accelerator,
    LabelKey,
    QueueName,
    RequestField,
)

MINIMAL_CONFIG = JobConfig(
    entry_point="dr_exp.training.dummy_trainer:train",
    params={"epochs": 3},
    labels={"accelerator": "cpu"},
)


def test_execution_config_document_is_pinned() -> None:
    assert execution_config_document() == {
        "pipeline": "dr-exp-train",
        "version": 1,
        "trainer_contract": "dr-exp/importable-json/v1",
    }


def test_execution_config_reference_is_pinned() -> None:
    assert execution_config_reference() == (
        "116244a77518ca092a7a84005b79a71f7f13269b7c13d10f7bfefefd9728c40e"
    )


def test_work_identity_document_is_pinned() -> None:
    assert work_identity_document(MINIMAL_CONFIG) == {
        "entry_point": "dr_exp.training.dummy_trainer:train",
        "labels": {"accelerator": "cpu"},
        "params": {"epochs": 3},
    }


def test_work_key_is_pinned() -> None:
    assert work_key(MINIMAL_CONFIG) == (
        "a8b984e1495ffaf89e7e86597b0c5c7e2ab554c462c21f7abecd230e83ef94f8"
    )


def test_work_identity_document_includes_budgets_only_when_set() -> None:
    with_budgets = MINIMAL_CONFIG.model_copy(
        update={"budgets": Budgets(wall_time_seconds=300)}
    )
    document = work_identity_document(with_budgets)
    assert document["budgets"] == {"wall_time_seconds": 300.0}
    assert "budgets" not in work_identity_document(MINIMAL_CONFIG)


def test_work_key_ignores_priority_and_tags() -> None:
    rescheduled = MINIMAL_CONFIG.model_copy(update={"priority": 7, "tags": ("rerun",)})
    assert work_key(rescheduled) == work_key(MINIMAL_CONFIG)


@pytest.mark.parametrize(
    "update",
    [
        {"entry_point": "dr_exp.training.dummy_trainer:other"},
        {"params": {"epochs": 4}},
        {"labels": {"accelerator": "mps"}},
        {"budgets": Budgets(wall_time_seconds=60)},
    ],
)
def test_work_key_changes_with_identity_bearing_fields(
    update: dict[str, object],
) -> None:
    changed = MINIMAL_CONFIG.model_copy(update=update)
    assert work_key(changed) != work_key(MINIMAL_CONFIG)


def test_work_key_is_a_valid_platform_key() -> None:
    from dr_platform import WorkKey

    assert WorkKey(work_key(MINIMAL_CONFIG)).value == work_key(MINIMAL_CONFIG)


def test_string_vocabularies_are_pinned() -> None:
    assert PIPELINE_KEY == "dr-exp-train"
    assert PIPELINE_VERSION == 1
    assert STAGE_KEY == "train"
    assert TRAINER_CONTRACT == "dr-exp/importable-json/v1"
    assert JOB_CONFIG_SCHEMA == "dr_exp.job_config/v1"
    assert [a.value for a in Accelerator] == ["cpu", "mps", "cuda"]
    assert [q.value for q in QueueName] == [
        "train-cpu",
        "train-mps",
        "train-cuda",
    ]
    assert [f.value for f in RequestField] == [
        "params",
        "workspace",
        "work_key",
        "attempt",
    ]
    assert LabelKey.ACCELERATOR.value == "accelerator"
