"""End-to-end lifecycle against a real PostgreSQL database.

Every wait in this module synchronizes on ledger or filesystem state with a
bounded watchdog. Reaching a watchdog is a failure to make progress, never
evidence that something happened.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

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
from dr_exp.training.dummy_trainer import PID_FILENAME, STARTED_FILENAME

pytestmark = pytest.mark.integration

#: Watchdog for anything that should settle promptly. Exceeding it is a bug.
WATCHDOG_SECONDS = 90.0
POLL_SECONDS = 0.1

#: Gate timeout for a trainer a test intends to cancel. It must comfortably
#: exceed every watchdog that test waits on: a trainer that gives up on its own
#: gate would exit without being torn down, and the cancellation assertions
#: would pass without cancellation ever having worked.
UNREACHABLE_GATE_TIMEOUT_SECONDS = 600.0

#: How long a cancelled child may take to die. dr-exec sends SIGTERM and
#: escalates to SIGKILL after the profile's termination grace, so this only
#: needs to cover that window plus process reaping.
CHILD_EXIT_WATCHDOG_SECONDS = 30.0

#: How long the cancelled trainer spends "checkpointing" after SIGTERM. A real
#: trainer does not exit instantly, and the stage body must not report
#: CANCELLED until dr-exec has finished tearing the child down. Comfortably
#: under the profile's termination grace, so SIGTERM -- not SIGKILL -- is what
#: ends the child.
TRAINER_SHUTDOWN_DELAY_SECONDS = 3.0

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


def process_alive(pid: int) -> bool:
    """Whether ``pid`` still names a live process.

    Signal 0 performs the permission and existence checks without delivering
    anything, which is the cheapest true liveness probe available here.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover -- same-user children only
        return True
    return True


def read_evidence(engine: Engine, reference: str) -> dict[str, Any]:
    """Resolve a stage-failure evidence reference to its stored document.

    dr-platform writes evidence into dr-store and records only the reference,
    so asserting on its content means reading it back the same way the
    dispatcher wrote it.
    """
    from dr_store import ObjectStore, parse_object_reference
    from dr_store.storage_backends.postgresql import PostgresBackend

    store = ObjectStore(PostgresBackend.open_sync(engine))
    with engine.connect() as connection:
        document = store.get_enlisted(connection, parse_object_reference(reference))
    assert isinstance(document, dict)
    return document


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

    # The reference must actually resolve to dr-exec's own account of the
    # failure. A trainer that raises never writes its JSON result, so dr-exec
    # reports `protocol_failed` and attributes it to the payload -- not to the
    # platform, which is the distinction an operator triages on.
    reference = members[0].evidence_reference
    assert reference is not None
    evidence = read_evidence(engine, reference)
    assert evidence["outcome"]["kind"] == "protocol_failed"
    assert evidence["attribution"]["owner"] == "payload"
    workspace = profile.workspace_for(compute_work_key(config), 1)
    assert evidence["workspace"] == str(workspace)


def test_a_non_json_trainer_result_is_attributed_to_the_payload(
    profile: MachineProfile, engine: Engine
) -> None:
    """The other half of the trainer contract: the result must be strict JSON.

    The trainer exits cleanly here, so the failure is caught at the result
    boundary rather than by the process outcome.
    """
    config = base_config(return_non_json=True)
    submit_jobs(
        (config,),
        campaign_key=CAMPAIGN,
        run_key="non-json",
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
    members = inspection.failed_run_members(engine, run_key="non-json")
    assert len(members) == 1
    reference = members[0].evidence_reference
    assert reference is not None
    evidence = read_evidence(engine, reference)
    assert evidence["attribution"]["owner"] == "payload"


def test_cancelling_an_in_flight_attempt_stops_its_child(
    profile: MachineProfile, running_worker: Engine, tmp_path: Path
) -> None:
    from dbos import DBOSClient
    from dr_platform import cancel_work

    engine = running_worker
    gate = tmp_path / "gate"
    config = base_config(
        gate_file=str(gate),
        gate_timeout_seconds=UNREACHABLE_GATE_TIMEOUT_SECONDS,
        shutdown_delay_seconds=TRAINER_SHUTDOWN_DELAY_SECONDS,
    )
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
    # The trainer writes its PID before the started marker, so it is readable
    # by the time that marker exists.
    child_pid = int((profile.workspace_for(key, 1) / PID_FILENAME).read_text())
    assert process_alive(child_pid), "the trainer child was gone before cancelling"

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
    # The ledger saying CANCELLED proves nothing about the child: a trainer
    # still blocked on its gate leaves exactly the same workspace behind, and
    # its gate here outlasts every watchdog in this test, so the only way it
    # exits is by being torn down. DBOS writes the CANCELLED row from its own
    # poller before the stage body finishes, so this is a bounded wait rather
    # than an immediate assertion.
    wait_until(
        lambda: not process_alive(child_pid),
        what=f"the trainer child {child_pid} to be torn down",
        timeout=CHILD_EXIT_WATCHDOG_SECONDS,
    )
    # The gate was never opened, so a surviving child would still be waiting
    # on it and could not have written a result.
    assert not gate.exists()
    assert not (profile.workspace_for(key, 1) / RESULT_FILENAME).exists()


def declared_train_queues() -> frozenset[str]:
    """The train queues this process has declared to DBOS.

    Declaring a DBOS ``Queue`` is what starts a listener thread, and the
    in-memory registry is where that declaration lands -- so it, not the
    database, is where "did this process declare a queue" is answerable.
    """
    from dbos._dbos import _get_or_create_dbos_registry

    from dr_exp.config.names import QueueName

    declared = frozenset(_get_or_create_dbos_registry().queue_info_map)
    return declared & frozenset(queue.value for queue in QueueName)


def test_a_dispatcher_only_runtime_declares_no_train_queue(
    profile: MachineProfile, engine: Engine
) -> None:
    """`declare_queues=False` is the whole difference between the two roles.

    A declared queue starts a listener that dequeues and runs work, so a
    dispatcher that declared one would execute training work as well as
    dispatch it -- silently, since nothing else about the process changes.
    """
    with worker_runtime(
        profile, with_dispatcher=True, declare_queues=False, forward_signals=False
    ):
        assert declared_train_queues() == frozenset()


def test_a_worker_runtime_declares_the_queues_it_drains(
    profile: MachineProfile, engine: Engine
) -> None:
    """The control for the test above: the default really does declare them."""
    with worker_runtime(profile, with_dispatcher=True, forward_signals=False):
        assert declared_train_queues() == frozenset(
            queue.value for queue in profile.dequeued_queue_names
        )


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


def dbos_workflow_rows(engine: Engine) -> tuple[dict[str, Any], ...]:
    """The DBOS rows for this pipeline's stage workflows, oldest first.

    Priority only exists once admission enqueues a workflow, so this is where
    the queue-level effect of `priority` is observable at all. dr-platform's
    own scheduled dispatcher workflows share the table and are excluded by
    queue name.
    """
    from sqlalchemy import text

    from dr_exp.config.names import QueueName

    train_queues = tuple(queue.value for queue in QueueName)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT workflow_uuid, status, priority, started_at_epoch_ms "
                "FROM dbos.workflow_status "
                "WHERE queue_name = ANY(:queues) "
                "ORDER BY started_at_epoch_ms"
            ),
            {"queues": list(train_queues)},
        ).mappings()
        return tuple(dict(row) for row in rows)


def test_priority_orders_admitted_work_on_a_single_slot_worker(
    profile: MachineProfile, engine: Engine, tmp_path: Path
) -> None:
    """Lower priority runs sooner, which is dr-platform's direction.

    Both items are submitted before any worker exists and held behind one
    concurrency slot, so the queue -- not submission order or timing -- decides
    which trainer starts first. The urgent job is submitted *second* so that
    passing cannot be an artifact of insertion order.
    """
    single_slot = profile.model_copy(update={"worker_concurrency": 1})
    background = base_config(seed=1, priority_marker="background")
    urgent = base_config(seed=2, priority_marker="urgent")
    background_key = compute_work_key(background)
    urgent_key = compute_work_key(urgent)

    # One run: a run's expected member count is declared at submission, so
    # both points must be registered together.
    submit_jobs(
        (
            background.model_copy(update={"priority": 200}),
            urgent.model_copy(update={"priority": 1}),
        ),
        campaign_key=CAMPAIGN,
        run_key="priority",
        profile=single_slot,
        engine=engine,
    )

    with worker_runtime(single_slot, with_dispatcher=True) as runtime:
        summary = drain_until(
            engine=runtime.engine,
            campaign_key=CAMPAIGN,
            cancellation=runtime.cancellation,
            max_jobs=2,
            deadline_seconds=WATCHDOG_SECONDS,
        )

    assert summary.reached_limit
    assert set(states(engine).values()) == {StageExecutionState.SUCCEEDED}

    # The queue carried the priorities through to DBOS rather than defaulting
    # them, which is what `priority_enabled=True` on the queue buys.
    priorities = sorted(row["priority"] for row in dbos_workflow_rows(engine))
    assert priorities == [1, 200]

    # And the urgent job's trainer really started first.
    urgent_started = single_slot.workspace_for(urgent_key, 1) / STARTED_FILENAME
    background_started = single_slot.workspace_for(background_key, 1) / STARTED_FILENAME
    assert urgent_started.stat().st_mtime_ns < background_started.stat().st_mtime_ns


def test_boost_reprioritises_an_admitted_item_in_dbos(
    profile: MachineProfile, running_worker: Engine, tmp_path: Path
) -> None:
    """Boost must reach the DBOS queue row, not just the dr-exp ledger.

    An item is only enqueued once admission has run, so this boosts a job that
    a live worker has already admitted and is holding on its gate.
    """
    engine = running_worker
    gate = tmp_path / "boost-gate"
    config = base_config(gate_file=str(gate), gate_timeout_seconds=WATCHDOG_SECONDS)
    key = compute_work_key(config)
    submit_jobs(
        (config,),
        campaign_key=CAMPAIGN,
        run_key="boosted-live",
        profile=profile,
        engine=engine,
    )

    started = profile.workspace_for(key, 1) / STARTED_FILENAME
    wait_until(started.exists, what="the trainer child to start")

    rows = dbos_workflow_rows(engine)
    assert len(rows) == 1
    assert rows[0]["priority"] == config.priority

    result = set_work_priority(
        campaign_key=CAMPAIGN, work_key=key, priority=3, engine=engine
    )
    assert result.priority == 3

    item = inspection.resolve_work_item(engine, campaign_key=CAMPAIGN, work_key=key)
    stages = inspection.work_item_stages(engine, work_item_id=item.work_item_id)
    assert stages[0].execution.priority == 3

    # The dr-exp ledger agreeing is not the claim under test: a boost that
    # never reached DBOS would leave the queue row at its original priority
    # and the item would still be dequeued in its old order.
    boosted = dbos_workflow_rows(engine)
    assert len(boosted) == 1
    assert boosted[0]["priority"] == 3

    # Let the trainer finish so the worker fixture can shut down cleanly.
    gate.write_text("open")
    wait_until(
        lambda: states(engine).get(key) is StageExecutionState.SUCCEEDED,
        what="the boosted work item to succeed",
    )


def test_retry_creates_a_new_attempt_that_can_succeed(
    profile: MachineProfile, engine: Engine, tmp_path: Path
) -> None:
    """An operator retry is the recovery path for an application failure.

    The trainer fails while a sentinel file is absent, so the first attempt
    fails for a real reason and the retried attempt succeeds against the same
    work item -- no resubmission, no new work key.
    """
    from dr_platform import retry_stage

    sentinel = tmp_path / "trainer-fixed"
    config = base_config(fail_until_file=str(sentinel))
    key = compute_work_key(config)
    submit_jobs(
        (config,),
        campaign_key=CAMPAIGN,
        run_key="retried",
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
    assert states(engine) == {key: StageExecutionState.FAILED}

    item = inspection.resolve_work_item(engine, campaign_key=CAMPAIGN, work_key=key)
    failed = inspection.work_item_stages(engine, work_item_id=item.work_item_id)[0]
    assert failed.execution.state is StageExecutionState.FAILED
    assert len(failed.attempts) == 1

    # Fix the trainer, then retry the failed stage.
    sentinel.write_text("fixed")
    result = retry_stage(failed.execution.stage_execution_id, engine=engine)
    assert result.new_attempt.attempt_number == 2

    with worker_runtime(profile, with_dispatcher=True) as runtime:
        summary = drain_until(
            engine=runtime.engine,
            campaign_key=CAMPAIGN,
            cancellation=runtime.cancellation,
            max_jobs=1,
            deadline_seconds=WATCHDOG_SECONDS,
        )

    assert summary.reached_limit, "the retried attempt did not finish"
    assert states(engine) == {key: StageExecutionState.SUCCEEDED}

    # The retry ran as a genuinely separate attempt, in its own workspace.
    stages = inspection.work_item_stages(engine, work_item_id=item.work_item_id)
    assert len(stages[0].attempts) == 2
    written = json.loads((profile.workspace_for(key, 2) / RESULT_FILENAME).read_text())
    assert written["attempt"] == 2
    assert not (profile.workspace_for(key, 1) / RESULT_FILENAME).exists()


def test_worker_shutdown_tears_down_its_in_flight_child(
    profile: MachineProfile, engine: Engine, tmp_path: Path
) -> None:
    """Leaving `worker_runtime` must not strand a running trainer.

    This is the shutdown path rather than the operator-cancel path: nothing
    has cancelled the *workflow*, so DBOS is not reaping anything on dr-exp's
    behalf. The worker cancels its own registry, waits for the stage bodies to
    finish, and only then destroys the runtime -- so the child must be gone by
    the time the context manager returns.
    """
    gate = tmp_path / "shutdown-gate"
    config = base_config(
        gate_file=str(gate),
        gate_timeout_seconds=UNREACHABLE_GATE_TIMEOUT_SECONDS,
        shutdown_delay_seconds=TRAINER_SHUTDOWN_DELAY_SECONDS,
    )
    key = compute_work_key(config)
    submit_jobs(
        (config,),
        campaign_key=CAMPAIGN,
        run_key="shutdown",
        profile=profile,
        engine=engine,
    )

    started = profile.workspace_for(key, 1) / STARTED_FILENAME
    with worker_runtime(profile, with_dispatcher=True, forward_signals=False):
        wait_until(started.exists, what="the trainer child to start")
        child_pid = int((profile.workspace_for(key, 1) / PID_FILENAME).read_text())
        assert process_alive(child_pid)

    # The gate never opened, so the only thing that can have ended this child
    # is the worker's own shutdown.
    assert not gate.exists()
    assert not process_alive(child_pid), (
        f"worker shutdown returned while trainer child {child_pid} was still running"
    )
