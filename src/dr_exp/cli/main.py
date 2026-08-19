"""The ``dr_exp`` command line.

Every command resolves a machine profile first: the profile owns the database,
the interpreter, and the filesystem roots, so no command carries a host-specific
default of its own.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click

from dr_exp.config.identity import work_key as compute_work_key
from dr_exp.config.job import (
    DEFAULT_PRIORITY,
    ConfigError,
    JobConfig,
    load_job_config,
    load_sweep_spec,
)
from dr_exp.config.machine import MachineProfile, load_machine_profile
from dr_exp.config.names import LabelKey
from dr_exp.platform import inspection
from dr_exp.platform.database import engine_for, initialize_schema
from dr_exp.platform.submission import submit_jobs

#: Default campaign for commands invoked without an explicit one.
DEFAULT_CAMPAIGN_KEY = "default"

_MACHINE_OPTION = click.option(
    "--machine",
    "machine",
    required=True,
    help="Machine profile name or path to a profile YAML.",
)
_CAMPAIGN_OPTION = click.option(
    "--campaign",
    "campaign_key",
    default=DEFAULT_CAMPAIGN_KEY,
    show_default=True,
    help="Campaign the work belongs to.",
)


def _profile(machine: str) -> MachineProfile:
    try:
        return load_machine_profile(machine)
    except (ConfigError, ValueError) as error:
        raise click.ClickException(str(error)) from error


def _fail(error: Exception) -> None:
    raise click.ClickException(str(error)) from error


class _OperatorErrorGroup(click.Group):
    """A group that reports operator mistakes without a traceback.

    Bad input reaches dr-exp as three unrelated exception families: pydantic
    and dr-exp validation raise ``ValueError``, dr-platform's ledger conflicts
    (``PipelineRunConflictError``, ``RegistrationClosureError``, and their
    siblings) are ``RuntimeError``s, and inspection raises ``LookupError`` for
    a key that does not exist. None of them is a dr-exp bug, so all of them
    become a ``ClickException`` here rather than a stack trace at the terminal.
    """

    def invoke(self, ctx: click.Context) -> Any:  # noqa: ANN401 -- click's type
        try:
            return super().invoke(ctx)
        except click.ClickException:
            raise
        except (LookupError, RuntimeError, ValueError) as error:
            raise click.ClickException(_operator_message(error)) from error


def _operator_message(error: Exception) -> str:
    """Render an operator-facing message for a non-bug failure."""
    message = str(error) or error.__class__.__name__
    if isinstance(error, LookupError) and not isinstance(error, KeyError):
        return message
    if isinstance(error, KeyError):
        return f"not found: {message}"
    return message


@click.group(cls=_OperatorErrorGroup)
@click.version_option(package_name="dr-exp")
def cli() -> None:
    """dr_exp - durable experiment manager for local and cluster training."""


@cli.command()
@_MACHINE_OPTION
def init(machine: str) -> None:
    """Create the platform schema and this machine's filesystem roots."""
    profile = _profile(machine)
    profile.workspace_root.mkdir(parents=True, exist_ok=True)
    profile.run_store_root.mkdir(parents=True, exist_ok=True)
    initialize_schema(profile)
    click.echo(f"Initialized {profile.name} at {profile.database_url}")
    click.echo(f"  workspace_root: {profile.workspace_root}")
    click.echo(f"  run_store_root: {profile.run_store_root}")


@cli.command()
@_MACHINE_OPTION
@_CAMPAIGN_OPTION
@click.option("--run", "run_key", required=True, help="Run key for this batch.")
@click.option(
    "--priority",
    type=int,
    default=None,
    help=(
        "Override the config priority. Lower is sooner; 0 is highest. "
        f"Configs default to {DEFAULT_PRIORITY}."
    ),
)
@click.argument(
    "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
def submit(
    machine: str,
    campaign_key: str,
    run_key: str,
    priority: int | None,
    config_path: Path,
) -> None:
    """Submit one job configuration."""
    profile = _profile(machine)
    try:
        config = load_job_config(config_path)
    except (ConfigError, ValueError) as error:
        _fail(error)
    _submit(
        (_with_priority(config, priority),),
        profile=profile,
        campaign_key=campaign_key,
        run_key=run_key,
    )


@cli.command()
@_MACHINE_OPTION
@_CAMPAIGN_OPTION
@click.option("--run", "run_key", required=True, help="Run key for this sweep.")
@click.option(
    "--priority",
    type=int,
    default=None,
    help="Override the base config priority for every point.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the expanded configurations without submitting them.",
)
@click.argument(
    "spec_path", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
def sweep(
    machine: str,
    campaign_key: str,
    run_key: str,
    priority: int | None,
    dry_run: bool,
    spec_path: Path,
) -> None:
    """Expand a sweep specification and submit every point."""
    profile = _profile(machine)
    try:
        configs = tuple(
            _with_priority(config, priority)
            for config in load_sweep_spec(spec_path).expand()
        )
    except (ConfigError, ValueError) as error:
        _fail(error)

    if dry_run:
        for config in configs:
            click.echo(f"{compute_work_key(config)[:12]}  {config.params}")
        click.echo(f"{len(configs)} configuration(s)")
        return
    _submit(configs, profile=profile, campaign_key=campaign_key, run_key=run_key)


def _with_priority(config: JobConfig, priority: int | None) -> JobConfig:
    if priority is None:
        return config
    return config.model_copy(update={"priority": priority})


def _submit(
    configs: tuple[JobConfig, ...],
    *,
    profile: MachineProfile,
    campaign_key: str,
    run_key: str,
) -> None:
    with engine_for(profile) as engine:
        try:
            result = submit_jobs(
                configs,
                campaign_key=campaign_key,
                run_key=run_key,
                profile=profile,
                engine=engine,
            )
        except (ConfigError, ValueError) as error:
            _fail(error)
    receipt = result.receipt
    click.echo(
        f"Submitted run {receipt.run_key.value} to campaign {campaign_key}: "
        f"{receipt.registered_member_count} member(s), "
        f"{receipt.created_work_count} new, "
        f"{receipt.reused_work_count} reused"
    )
    for key in result.work_keys:
        click.echo(f"  {key[:12]}")


@cli.command(name="list")
@_MACHINE_OPTION
@click.option(
    "--campaign",
    "campaign_key",
    default=None,
    help="Restrict output to one campaign.",
)
def list_campaigns(machine: str, campaign_key: str | None) -> None:
    """List campaigns with their work-state counts."""
    profile = _profile(machine)
    with engine_for(profile) as engine:
        overviews = inspection.overview(engine, campaign_key=campaign_key)
    if not overviews:
        click.echo("No campaigns found.")
        return
    for item in overviews:
        counts = " ".join(
            f"{state}={count}" for state, count in sorted(item.state_counts.items())
        )
        click.echo(
            f"{item.summary.campaign_key.value}  "
            f"runs={item.summary.run_count} "
            f"work={item.summary.work_item_count}  {counts}"
        )


@cli.command()
@_MACHINE_OPTION
@_CAMPAIGN_OPTION
@click.option("--run", "run_key", default=None, help="Show one run's members.")
def status(machine: str, campaign_key: str, run_key: str | None) -> None:
    """Show campaign or run status."""
    profile = _profile(machine)
    with engine_for(profile) as engine:
        if run_key is None:
            runs = inspection.campaign_runs(engine, campaign_key=campaign_key)
            overviews = inspection.overview(engine, campaign_key=campaign_key)
            if not overviews:
                click.echo(f"No campaign named {campaign_key!r}.")
                return
            counts = overviews[0].state_counts
            click.echo(f"Campaign {campaign_key}")
            for state, count in sorted(counts.items()):
                click.echo(f"  {state:>10}: {count}")
            click.echo(f"  runs: {', '.join(runs) if runs else '(none)'}")
            return
        counts = inspection.run_overview(engine, run_key=run_key)
        click.echo(f"Run {run_key}")
        for state, count in sorted(counts.items()):
            click.echo(f"  {state:>10}: {count}")
        for member in inspection.run_members(engine, run_key=run_key):
            state = member.state.value if member.state else "unknown"
            click.echo(
                f"  [{member.member_ordinal:>3}] {member.work_key.value[:12]}  {state}"
            )


@cli.command()
@_MACHINE_OPTION
@_CAMPAIGN_OPTION
@click.argument("work_key")
def show(machine: str, campaign_key: str, work_key: str) -> None:
    """Show one work item's stages and attempts."""
    profile = _profile(machine)
    with engine_for(profile) as engine:
        item = _resolve(engine, campaign_key=campaign_key, work_key=work_key)
        click.echo(f"work_key: {item.work_key.value}")
        click.echo(f"work_item_id: {item.work_item_id}")
        click.echo(f"labels: {dict(item.labels)}")
        click.echo(f"state: {item.state.value}")
        for stage in inspection.work_item_stages(
            engine, work_item_id=item.work_item_id
        ):
            execution = stage.execution
            click.echo(
                f"  stage {execution.stage_key.value} "
                f"[{execution.stage_index}] {execution.state.value} "
                f"priority={execution.priority}"
            )
            for attempt in stage.attempts:
                summary = attempt.terminal_summary or {}
                message = summary.get("message", "")
                click.echo(
                    f"    attempt {attempt.attempt_number}: "
                    f"{summary.get('outcome', 'pending')} {message}"
                )
            if execution.output_reference:
                click.echo(f"    output: {execution.output_reference}")


def _resolve(engine: Any, *, campaign_key: str, work_key: str) -> Any:  # noqa: ANN401
    try:
        return inspection.resolve_work_item(
            engine, campaign_key=campaign_key, work_key=work_key
        )
    except ConfigError as error:
        raise click.ClickException(str(error)) from error


@cli.command()
@_MACHINE_OPTION
@_CAMPAIGN_OPTION
@click.argument("work_key")
def cancel(machine: str, campaign_key: str, work_key: str) -> None:
    """Cancel one work item, interrupting it if it is running."""
    from dbos import DBOSClient
    from dr_platform import cancel_work

    profile = _profile(machine)
    with engine_for(profile) as engine:
        item = _resolve(engine, campaign_key=campaign_key, work_key=work_key)
        client = DBOSClient(system_database_url=profile.system_database_url)
        try:
            result = cancel_work(
                engine=engine,
                client=client,
                work_item_id=item.work_item_id,
            )
        finally:
            client.destroy()
    click.echo(f"Cancelled {item.work_key.value[:12]}")
    for cancellation in result.cancellations:
        click.echo(
            f"  stage {cancellation.stage_execution.stage_key.value}: "
            f"{cancellation.disposition.value}"
        )


@cli.command()
@_MACHINE_OPTION
@_CAMPAIGN_OPTION
@click.option(
    "--priority",
    type=int,
    required=True,
    help="New priority. Lower is sooner; 0 is highest.",
)
@click.argument("work_key")
def boost(machine: str, campaign_key: str, priority: int, work_key: str) -> None:
    """Change one work item's admission priority."""
    from dr_platform import set_work_priority

    profile = _profile(machine)
    with engine_for(profile) as engine:
        item = _resolve(engine, campaign_key=campaign_key, work_key=work_key)
        result = set_work_priority(
            campaign_key=campaign_key,
            work_key=item.work_key,
            priority=priority,
            engine=engine,
        )
    click.echo(
        f"{item.work_key.value[:12]} priority={result.priority} "
        f"({len(result.updated_stage_execution_ids)} stage(s) updated)"
    )


@cli.command()
@_MACHINE_OPTION
@_CAMPAIGN_OPTION
@click.argument("work_key")
def retry(machine: str, campaign_key: str, work_key: str) -> None:
    """Create a new attempt for one work item's failed stage."""
    from dr_platform import StageExecutionState, retry_stage

    profile = _profile(machine)
    with engine_for(profile) as engine:
        item = _resolve(engine, campaign_key=campaign_key, work_key=work_key)
        failed = [
            stage.execution
            for stage in inspection.work_item_stages(
                engine, work_item_id=item.work_item_id
            )
            if stage.execution.state is StageExecutionState.FAILED
        ]
        if not failed:
            raise click.ClickException(
                f"{item.work_key.value[:12]} has no failed stage to retry"
            )
        for execution in failed:
            result = retry_stage(execution.stage_execution_id, engine=engine)
            click.echo(
                f"{item.work_key.value[:12]} stage "
                f"{execution.stage_key.value}: attempt "
                f"{result.new_attempt.attempt_number}"
            )


@cli.command()
@_MACHINE_OPTION
@click.option(
    "--accelerator",
    default=None,
    help="Pause only work labelled with this accelerator.",
)
def pause(machine: str, accelerator: str | None) -> None:
    """Stop admitting new training work."""
    _set_paused(machine, accelerator=accelerator, paused=True)


@cli.command()
@_MACHINE_OPTION
@click.option(
    "--accelerator",
    default=None,
    help="Resume only work labelled with this accelerator.",
)
def resume(machine: str, accelerator: str | None) -> None:
    """Resume admitting training work."""
    _set_paused(machine, accelerator=accelerator, paused=False)


def _set_paused(machine: str, *, accelerator: str | None, paused: bool) -> None:
    from dr_platform import pause as pause_stage
    from dr_platform import resume as resume_stage

    from dr_exp.platform.pipeline import PIPELINE_IDENTITY, TRAIN_STAGE_KEY

    profile = _profile(machine)
    labels = None if accelerator is None else {LabelKey.ACCELERATOR.value: accelerator}
    action = pause_stage if paused else resume_stage
    with engine_for(profile) as engine:
        try:
            record = action(
                pipeline=PIPELINE_IDENTITY,
                stage_key=TRAIN_STAGE_KEY,
                labels=labels,
                engine=engine,
            )
        except LookupError as error:
            raise click.ClickException(
                "no capacity control exists for that selector; run "
                "'dr_exp capacity' first"
            ) from error
    click.echo(
        f"train {dict(record.selector) or '(default)'}: "
        f"paused={record.paused} capacity={record.capacity}"
    )


@cli.command()
@_MACHINE_OPTION
@click.option(
    "--accelerator",
    default=None,
    help="Set capacity for one accelerator instead of the stage default.",
)
@click.option(
    "--capacity", type=int, default=None, help="New concurrent-admission limit."
)
def capacity(machine: str, accelerator: str | None, capacity: int | None) -> None:
    """Show or set admission capacity for the train stage."""
    from dr_platform import (
        read_controls,
        set_selector_capacity,
        set_stage_capacity,
    )

    from dr_exp.platform.pipeline import PIPELINE_IDENTITY, TRAIN_STAGE_KEY

    profile = _profile(machine)
    with engine_for(profile) as engine:
        if capacity is not None:
            if accelerator is None:
                set_stage_capacity(
                    pipeline=PIPELINE_IDENTITY,
                    stage_key=TRAIN_STAGE_KEY,
                    capacity=capacity,
                    engine=engine,
                )
            else:
                set_selector_capacity(
                    pipeline=PIPELINE_IDENTITY,
                    stage_key=TRAIN_STAGE_KEY,
                    labels={LabelKey.ACCELERATOR.value: accelerator},
                    capacity=capacity,
                    engine=engine,
                )
        for record in read_controls(
            pipeline=PIPELINE_IDENTITY,
            stage_key=TRAIN_STAGE_KEY,
            engine=engine,
        ):
            selector = dict(record.selector) or "(default)"
            click.echo(f"{selector}: capacity={record.capacity} paused={record.paused}")


@cli.command()
@_MACHINE_OPTION
@_CAMPAIGN_OPTION
@click.option(
    "--with-dispatcher",
    is_flag=True,
    help="Also run admission and reconciliation in this process.",
)
@click.option(
    "--max-jobs",
    type=int,
    default=None,
    help="Exit once this many work items in the campaign are terminal.",
)
@click.option(
    "--deadline-seconds",
    type=float,
    default=None,
    help="Watchdog: give up waiting after this long. Reaching it is a failure.",
)
def worker(
    machine: str,
    campaign_key: str,
    with_dispatcher: bool,
    max_jobs: int | None,
    deadline_seconds: float | None,
) -> None:
    """Run a worker that executes training attempts."""
    from dr_exp.platform.drain import drain_until
    from dr_exp.platform.worker import worker_runtime

    profile = _profile(machine)
    click.echo(
        f"Worker {profile.executor_id} on {profile.name} draining "
        f"{', '.join(q.value for q in profile.dequeued_queue_names)} "
        f"(concurrency {profile.worker_concurrency})"
    )
    with worker_runtime(profile, with_dispatcher=with_dispatcher) as runtime:
        summary = drain_until(
            engine=runtime.engine,
            campaign_key=campaign_key,
            cancellation=runtime.cancellation,
            max_jobs=max_jobs,
            deadline_seconds=deadline_seconds,
        )
    click.echo(
        f"Worker stopped: {summary.terminal_count} terminal, "
        f"limit_reached={summary.reached_limit} "
        f"interrupted={summary.interrupted}"
    )
    if max_jobs is not None and not summary.reached_limit:
        sys.exit(1)


@cli.command()
@_MACHINE_OPTION
@click.option(
    "--deadline-seconds",
    type=float,
    default=None,
    help="Watchdog: stop after this long instead of running indefinitely.",
)
def dispatcher(machine: str, deadline_seconds: float | None) -> None:
    """Run admission and reconciliation without executing training work."""
    from dr_exp.platform.drain import drain_until
    from dr_exp.platform.worker import worker_runtime

    profile = _profile(machine)
    click.echo(f"Dispatcher {profile.executor_id} on {profile.name}")
    # No queues: declaring one would start a listener and this process would
    # execute training work as well as dispatch it.
    with worker_runtime(profile, with_dispatcher=True, declare_queues=False) as runtime:
        drain_until(
            engine=runtime.engine,
            campaign_key=DEFAULT_CAMPAIGN_KEY,
            cancellation=runtime.cancellation,
            max_jobs=None,
            deadline_seconds=deadline_seconds,
        )
    click.echo("Dispatcher stopped.")


def main() -> None:
    """Entry point for the ``dr_exp`` script."""
    cli()


if __name__ == "__main__":
    main()
