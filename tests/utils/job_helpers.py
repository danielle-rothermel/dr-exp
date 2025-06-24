"""Job creation test utilities."""

from typing import Any
from dr_exp.core.job_db import JobDB


def create_test_job(job_db: JobDB, priority: int = 100, **kwargs: Any) -> str:
    config = {"_target_": "dr_exp.trainers.test_trainer.train", "epochs": 10, **kwargs}
    return job_db.create_job(config, priority=priority)


def create_test_config(**overrides: Any) -> dict[str, Any]:
    base = {"_target_": "dr_exp.trainers.test_trainer.train", "epochs": 10, "lr": 0.001}
    base.update(overrides)
    return base


def create_multiple_jobs(
    job_db: JobDB, count: int, priority_start: int = 100, priority_step: int = 50
) -> list[str]:
    job_ids = []
    for i in range(count):
        job_id = create_test_job(
            job_db, priority=priority_start + i * priority_step, index=i
        )
        job_ids.append(job_id)
    return job_ids
