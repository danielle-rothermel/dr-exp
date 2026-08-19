"""The dr-exp worker process: a DBOS runtime that drains training queues.

Startup order is load-bearing:

* dr-platform's ``build_dbos_config`` does not expose DBOS's ``executor_id``
  or ``application_version``, and DBOS itself does not settle an application
  version until ``DBOS.launch()``. The sweep, however, needs both *before*
  launch, when ``register_scheduled_dispatcher`` captures them in a
  ``LiveDbosIdentity``. A mismatch makes the sweep read every live attempt as
  ``stale_app_version`` and fail it. So dr-exp pins both through
  ``initialize_dbos_runtime``'s ``runtime_initializer`` hook.
* dr-platform then requires that wrapped workflows, application queues, and
  the scheduled dispatcher all be registered before ``DBOS.launch()``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from dbos import DBOSConfig
from sqlalchemy import Engine

from dr_exp.config.machine import MachineProfile
from dr_exp.config.names import LabelKey
from dr_exp.execution.cancellation import AttemptCancellationRegistry
from dr_exp.platform.version import application_version

#: DBOS application name. Installations share a database by campaign, not by
#: application identity.
APP_NAME = "dr-exp"

#: Recovery cap for wrapped stage workflows. Past this, the sweep projects
#: platform failure and the work waits for an operator ``dr_exp retry``.
DEFAULT_MAX_RECOVERY_ATTEMPTS = 3

#: Admission and barrier batch sizes for a single local machine. dr-platform
#: requires the DBOS application pool to be at least the largest batch size.
LOCAL_BATCH_SIZE = 256
LOCAL_POOL_SIZE = 256


def _runtime_initializer(
    *, executor_id: str, app_version: str
) -> Callable[[DBOSConfig], None]:
    """Return a DBOS initializer that pins this process's identity.

    DBOS copies ``executor_id`` and ``application_version`` out of its config
    into process globals while constructing the runtime. That is the only
    supported way to pin them, since the corresponding environment variables
    are read when ``dbos`` is first imported -- which dr-platform has already
    done by the time a worker starts.
    """

    def initialize(config: DBOSConfig) -> None:
        from dbos import DBOS

        DBOS(
            config={
                **config,
                "executor_id": executor_id,
                "application_version": app_version,
            }
        )

    return initialize


@dataclass(frozen=True, slots=True)
class WorkerRuntime:
    """A launched worker and the resources bound to it."""

    profile: MachineProfile
    engine: Engine
    cancellation: AttemptCancellationRegistry
    dispatcher_enabled: bool


def ensure_stage_capacity(profile: MachineProfile, *, engine: Engine) -> None:
    """Give the train stage a default and per-accelerator admission capacity.

    Admission skips any stage lacking an empty-selector control, so a
    first-run worker would otherwise never see its own work. Controls that
    already exist are left alone -- capacity is an operator decision once it
    has been made.
    """
    from dr_platform import (
        read_controls,
        set_selector_capacity,
        set_stage_capacity,
    )

    from dr_exp.platform.pipeline import PIPELINE_IDENTITY, TRAIN_STAGE_KEY

    existing = read_controls(
        pipeline=PIPELINE_IDENTITY, stage_key=TRAIN_STAGE_KEY, engine=engine
    )
    selectors = {tuple(sorted(control.selector.items())) for control in existing}

    if () not in selectors:
        set_stage_capacity(
            pipeline=PIPELINE_IDENTITY,
            stage_key=TRAIN_STAGE_KEY,
            capacity=profile.worker_concurrency,
            engine=engine,
        )

    accelerator_selector = {LabelKey.ACCELERATOR.value: profile.accelerator.value}
    if tuple(sorted(accelerator_selector.items())) not in selectors:
        set_selector_capacity(
            pipeline=PIPELINE_IDENTITY,
            stage_key=TRAIN_STAGE_KEY,
            labels=accelerator_selector,
            capacity=profile.worker_concurrency,
            engine=engine,
        )


@contextmanager
def worker_runtime(
    profile: MachineProfile,
    *,
    with_dispatcher: bool,
    max_recovery_attempts: int = DEFAULT_MAX_RECOVERY_ATTEMPTS,
    forward_signals: bool = True,
) -> Iterator[WorkerRuntime]:
    """Start, launch, and tear down one worker's DBOS runtime.

    ``forward_signals`` installs the SIGTERM/SIGINT handler that drains
    in-flight attempts. It requires the main thread, so a test driving a
    worker from a helper thread turns it off and cancels the registry
    directly instead.
    """
    app_version = application_version()

    from dbos import DBOS, Queue
    from dr_platform import (
        LiveDbosIdentity,
        build_platform_dbos_config,
        initialize_dbos_runtime,
        register_scheduled_dispatcher,
    )

    from dr_exp.execution.cancellation import forward_shutdown_signals
    from dr_exp.platform.database import engine_for
    from dr_exp.platform.pipeline import StageContext, build_registry

    config = build_platform_dbos_config(
        database_url=profile.database_url,
        system_database_url=profile.system_database_url,
        max_recovery_attempts=max_recovery_attempts,
        pool_size=LOCAL_POOL_SIZE,
    )
    initialize_dbos_runtime(
        config,
        app_name=APP_NAME,
        runtime_initializer=_runtime_initializer(
            executor_id=profile.executor_id, app_version=app_version
        ),
    )

    cancellation = AttemptCancellationRegistry()
    registry = build_registry(
        StageContext(profile=profile, cancellation=cancellation),
        max_recovery_attempts=max_recovery_attempts,
    )

    for queue_name in profile.dequeued_queue_names:
        Queue(
            queue_name.value,
            priority_enabled=True,
            worker_concurrency=profile.worker_concurrency,
        )

    with engine_for(profile) as engine:
        dispatcher = None
        try:
            if with_dispatcher:
                dispatcher = register_scheduled_dispatcher(
                    config=config,
                    engine=engine,
                    registry=registry,
                    live_dbos_identity=LiveDbosIdentity(
                        app_version=app_version,
                        executor_ids=profile.sweeping_executor_ids,
                    ),
                    batch_size=LOCAL_BATCH_SIZE,
                    barrier_batch_size=LOCAL_BATCH_SIZE,
                    barrier_candidate_budget=LOCAL_BATCH_SIZE,
                    sweep_batch_size=LOCAL_BATCH_SIZE,
                )
            DBOS.launch()
            ensure_stage_capacity(profile, engine=engine)
            runtime = WorkerRuntime(
                profile=profile,
                engine=engine,
                cancellation=cancellation,
                dispatcher_enabled=dispatcher is not None,
            )
            if forward_signals:
                with forward_shutdown_signals(cancellation):
                    yield runtime
            else:
                yield runtime
        finally:
            if dispatcher is not None:
                dispatcher.close()
            # Clear the decorator registry too: this runtime's wrapped stage
            # workflows and queues were declared into it, and DBOS rejects a
            # second declaration of the same name in one process.
            DBOS.destroy(destroy_registry=True)


__all__ = [
    "APP_NAME",
    "DEFAULT_MAX_RECOVERY_ATTEMPTS",
    "LOCAL_BATCH_SIZE",
    "LOCAL_POOL_SIZE",
    "WorkerRuntime",
    "ensure_stage_capacity",
    "worker_runtime",
]
