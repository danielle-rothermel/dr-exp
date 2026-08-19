"""The priority convention dr-exp layers over dr-platform.

dr-platform admits lower numbers first and treats 0 as the highest priority.
dr-exp submits at a baseline of 100 so ``dr_exp boost`` has room to move work
ahead of everything already queued without touching other jobs.
"""

from __future__ import annotations

import pytest
from dr_platform import WorkInput
from dr_platform._core.validation import WORK_PRIORITY_MAX

from dr_exp.config.job import DEFAULT_PRIORITY, MAX_PRIORITY, JobConfig


def make_config(**overrides: object) -> JobConfig:
    fields: dict[str, object] = {
        "entry_point": "dr_exp.training.dummy_trainer:train",
        "labels": {"accelerator": "cpu"},
    }
    fields.update(overrides)
    return JobConfig.model_validate(fields)


def test_baseline_leaves_room_to_boost_and_to_defer() -> None:
    assert DEFAULT_PRIORITY == 100
    assert 0 < DEFAULT_PRIORITY < MAX_PRIORITY


def test_dr_exp_priority_range_matches_the_platform_range() -> None:
    assert MAX_PRIORITY == WORK_PRIORITY_MAX


def test_boosting_lowers_the_number() -> None:
    boosted = make_config(priority=10)
    assert boosted.priority < make_config().priority


def test_platform_accepts_the_baseline_priority() -> None:
    work = WorkInput(
        work_key="a" * 64,
        input_reference="/nonexistent/config.json",
        labels={"accelerator": "cpu"},
        priority=DEFAULT_PRIORITY,
    )
    assert work.priority == DEFAULT_PRIORITY


def test_platform_default_is_the_highest_priority() -> None:
    work = WorkInput(
        work_key="a" * 64,
        input_reference="/nonexistent/config.json",
        labels={"accelerator": "cpu"},
    )
    assert work.priority == 0


@pytest.mark.parametrize("priority", [-1, MAX_PRIORITY + 1])
def test_out_of_range_priorities_are_rejected_by_both_layers(
    priority: int,
) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        make_config(priority=priority)
    with pytest.raises(ValueError, match="priority"):
        WorkInput(
            work_key="a" * 64,
            input_reference="/nonexistent/config.json",
            labels={"accelerator": "cpu"},
            priority=priority,
        )
