"""End-to-end lifecycle against a real PostgreSQL database.

Every wait in this module synchronizes on ledger or filesystem state with a
bounded watchdog. Reaching a watchdog is a failure to make progress, never
evidence that something happened.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from dr_platform import StageExecutionState, set_work_priority
from sqlalchemy import Engine

from dr_exp.config.identity import work_key as compute_work_key
from dr_exp.config.job import JobConfig, SweepSpec
from dr_exp.config.machine import MachineProfile
from dr_exp.execution.attempt import RESULT_FILENAME
from dr_exp.platform import inspection
from dr_exp.platform.drain import drain_until
from dr_exp.platform.submission import submit_jobs
from dr_exp.platform.worker import worker_runtime
from dr_exp.training.dummy_trainer import STARTED_FILENAME

pytestmark = pytest.mark.integration

#: Watchdog for anything that should settle promptly. Exceeding it is a bug.
WATCHDOG_SECONDS = 90.0
POLL_SECONDS = 0.1

CAMPAIGN = "itest"


def base_config(**params: object) -> JobConfig:
    return JobConfig.model_validate(
        {
            "entry_point": "dr_exp.training.dummy_trainer:train",
            "params": {"epochs": 1, **params},
            "labels": {"accelerator": "cpu"},
        }
    )


def wait_until(
    predicate: Callable[[], bool], *, what: str, timeout: float = WATCHDOG_SECONDS
) -> None:
    """Block until ``predicate`` holds, failing the test if it never does."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(POLL_SECONDS)
    pytest.fail(f"timed out after {timeout}s waiting for {what}")


def states(engine: Engine) -> dict[str, StageExecutionState]:
    return {
        item.work_key.value: item.state
        for item in inspection.work_items(engine, campaign_key=CAMPAIGN)
    }


@pytest.fixture
def running_worker(profile: MachineProfile, engine: Engine) -> Iterator[Engine]:
    """A worker with its dispatcher, running on a background thread."""
    started = threading.Event()
    stopped = threading.Event()
    failure: list[BaseException] = []

    def run() -> None:
        try:
            # Signal forwarding needs the main thread, which this is not; the
            # fixture stops the worker through its stop event instead.
            with worker_runtime(profile, with_dispatcher=True, forward_signals=False):
                started.set()
                stopped.wait()
        except BaseException as error:
            failure.append(error)
            started.set()

    thread = threading.Thread(target=run, name="itest-worker", daemon=True)
    thread.start()
    assert started.wait(timeout=WATCHDOG_SECONDS), "worker never started"
    if failure:
        raise failure[0]
    try:
        yield engine
    finally:
        stopped.set()
        thread.join(timeout=WATCHDOG_SECONDS)
        if failure:
            raise failure[0]


def test_schema_initialization_is_idempotent(
    profile: MachineProfile, engine: Engine
) -> None:
    from dr_exp.platform.database import initialize_schema

    initialize_schema(profile)
    assert inspection.overview(engine) == ()


def test_sweep_submits_deduplicated_work(
    profile: MachineProfile, engine: Engine
) -> None:
    spec = SweepSpec(base=base_config(), grid={"seed": [1, 2]})
    result = submit_jobs(
        spec.expand(),
        campaign_key=CAMPAIGN,
        run_key="sweep",
        profile=profile,
        engine=engine,
    )
    assert result.receipt.registered_member_count == 2
    assert result.receipt.created_work_count == 2
    assert result.receipt.reused_work_count == 0
    assert states(engine) == dict.fromkeys(result.work_keys, StageExecutionState.READY)


def test_resubmitting_the_same_run_reuses_its_work(
    profile: MachineProfile, engine: Engine
) -> None:
    spec = SweepSpec(base=base_config(), grid={"seed": [1, 2]})
    first = submit_jobs(
        spec.expand(),
        campaign_key=CAMPAIGN,
        run_key="sweep",
        profile=profile,
        engine=engine,
    )
    second = submit_jobs(
        spec.expand(),
        campaign_key=CAMPAIGN,
        run_key="sweep",
        profile=profile,
        engine=engine,
    )
    assert second.receipt.created_work_count == first.receipt.created_work_count
    assert second.work_keys == first.work_keys
    assert len(states(engine)) == 2


def test_worker_runs_a_sweep_to_success(
    profile: MachineProfile, engine: Engine
) -> None:
    spec = SweepSpec(base=base_config(), grid={"seed": [1, 2]})
    result = submit_jobs(
        spec.expand(),
        campaign_key=CAMPAIGN,
        run_key="sweep",
        profile=profile,
        engine=engine,
    )

    with worker_runtime(profile, with_dispatcher=True) as runtime:
        summary = drain_until(
            engine=runtime.engine,
            campaign_key=CAMPAIGN,
            cancellation=runtime.cancellation,
            max_jobs=2,
            deadline_seconds=WATCHDOG_SECONDS,
        )

    assert summary.reached_limit, "sweep did not finish within the watchdog"
    assert set(states(engine).values()) == {StageExecutionState.SUCCEEDED}

    for key in result.work_keys:
        workspace = profile.workspace_for(key, 1)
        written = json.loads((workspace / RESULT_FILENAME).read_text())
        assert written["work_key"] == key
        assert written["epochs_completed"] == 1
        assert written["interrupted"] is False


def test_failing_trainer_records_failure_evidence(
    profile: MachineProfile, engine: Engine
) -> None:
    config = base_config(fail=True)
    submit_jobs(
        (config,),
        campaign_key=CAMPAIGN,
        run_key="failing",
        profile=profile,
        engine=engine,
    )

    with worker_runtime(profile, with_dispatcher=True) as runtime:
        drain_until(
            engine=runtime.engine,
            campaign_key=CAMPAIGN,
            cancellation=runtime.cancellation,
            max_jobs=1,
            deadline_seconds=WATCHDOG_SECONDS,
        )

    assert states(engine) == {compute_work_key(config): StageExecutionState.FAILED}
    # Terminal summaries and evidence references are only populated on the
    # filtered inspection path.
    members = inspection.failed_run_members(engine, run_key="failing")
    assert len(members) == 1
    summary = members[0].terminal_summary
    assert summary is not None
    assert summary["outcome"] == "failed"
    assert summary["producer"] == "application_failure"
    assert "StageApplicationFailure" in str(summary["error_type"])
    assert members[0].evidence_reference is not None


def test_cancelling_an_in_flight_attempt_stops_its_child(
    profile: MachineProfile, running_worker: Engine, tmp_path: Path
) -> None:
    from dbos import DBOSClient
    from dr_platform import cancel_work

    engine = running_worker
    gate = tmp_path / "gate"
    config = base_config(gate_file=str(gate), gate_timeout_seconds=WATCHDOG_SECONDS)
    key = compute_work_key(config)
    submit_jobs(
        (config,),
        campaign_key=CAMPAIGN,
        run_key="cancelled",
        profile=profile,
        engine=engine,
    )

    # The trainer writes this file before it blocks on the gate, so its
    # presence is evidence the child is really running.
    started = profile.workspace_for(key, 1) / STARTED_FILENAME
    wait_until(started.exists, what="the trainer child to start")

    item = inspection.resolve_work_item(engine, campaign_key=CAMPAIGN, work_key=key)
    client = DBOSClient(system_database_url=profile.system_database_url)
    try:
        result = cancel_work(
            engine=engine, client=client, work_item_id=item.work_item_id
        )
    finally:
        client.destroy()
    assert result.cancellations

    wait_until(
        lambda: states(engine).get(key) is StageExecutionState.CANCELLED,
        what="the work item to reach CANCELLED",
    )
    # The gate was never opened, so a surviving child would still be waiting
    # on it and could not have written a result.
    assert not gate.exists()
    assert not (profile.workspace_for(key, 1) / RESULT_FILENAME).exists()


def test_boost_lowers_priority_on_ready_work(
    profile: MachineProfile, engine: Engine
) -> None:
    config = base_config()
    key = compute_work_key(config)
    submit_jobs(
        (config,),
        campaign_key=CAMPAIGN,
        run_key="boosted",
        profile=profile,
        engine=engine,
    )
    item = inspection.resolve_work_item(engine, campaign_key=CAMPAIGN, work_key=key)
    before = inspection.work_item_stages(engine, work_item_id=item.work_item_id)
    assert before[0].execution.priority == config.priority

    result = set_work_priority(
        campaign_key=CAMPAIGN, work_key=key, priority=5, engine=engine
    )
    assert result.priority == 5

    after = inspection.work_item_stages(engine, work_item_id=item.work_item_id)
    assert after[0].execution.priority == 5
    assert after[0].execution.stage_execution_id in (result.updated_stage_execution_ids)
