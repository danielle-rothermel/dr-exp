"""SLURM job management commands."""

import json
import click


@click.group()
def slurm() -> None:
    """SLURM job management commands."""


@slurm.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show status of all SLURM jobs for this experiment."""
    # Create JobDB instance for this command
    from dr_exp.core.job_db import JobDB

    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )
    logs_dir = job_db.logs_dir

    if not logs_dir.exists():
        click.echo("No SLURM jobs found")
        return

    slurm_dirs = sorted([d for d in logs_dir.iterdir() if d.name.startswith("slurm_")])

    if not slurm_dirs:
        click.echo("No SLURM jobs found")
        return

    for slurm_dir in slurm_dirs:
        job_id = slurm_dir.name.replace("slurm_", "")
        status_file = job_db.control_dir / f"status_{job_id}.json"

        if status_file.exists():
            with status_file.open() as f:
                status = json.load(f)

            # Extract key info
            launcher_info = status.get("launcher", {})
            workers = status.get("workers", {})
            job_stats = status.get("jobs", {})

            # Count alive workers
            alive = sum(1 for w in workers.values() if w == "running")
            total = len(workers)

            runtime_hours = launcher_info.get("runtime_seconds", 0) / 3600

            click.echo(f"\nSLURM Job {job_id}")
            click.echo(f"  Node: {launcher_info.get('node', 'unknown')}")
            click.echo(f"  Runtime: {runtime_hours:.1f} hours")
            click.echo(f"  Workers: {alive}/{total} alive")
            click.echo(
                f"  Jobs: {job_stats.get('running', 0)} running, "
                f"{job_stats.get('queued', 0)} queued, "
                f"{job_stats.get('completed', 0)} completed"
            )
        else:
            click.echo(f"\nSLURM Job {job_id}: No status available")


@slurm.command()
@click.argument("job_id")
@click.option("--finish-current", is_flag=True, help="Finish current jobs then stop")
@click.option("--stop-now", is_flag=True, help="Stop immediately")
@click.pass_context
def control(
    ctx: click.Context, job_id: str, finish_current: bool, stop_now: bool
) -> None:
    """Send control commands to a SLURM job."""
    # Create JobDB instance for this command
    from dr_exp.core.job_db import JobDB

    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    if finish_current:
        control_file = job_db.control_dir / f"finish_current_{job_id}"
        control_file.touch()
        click.echo(f"Sent finish-current command to SLURM job {job_id}")
    elif stop_now:
        control_file = job_db.control_dir / f"stop_{job_id}"
        control_file.touch()
        click.echo(f"Sent stop command to SLURM job {job_id}")
    else:
        click.echo("Specify either --finish-current or --stop-now")


@slurm.command()
@click.argument("job_id")
@click.option("--tail", default=50, help="Number of lines to show")
@click.pass_context
def errors(ctx: click.Context, job_id: str, tail: int) -> None:
    """View aggregated errors from a SLURM job."""
    # Create JobDB instance for this command
    from dr_exp.core.job_db import JobDB

    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )
    error_log = job_db.logs_dir / f"slurm_{job_id}" / "errors.log"

    if not error_log.exists():
        click.echo(f"No errors found for SLURM job {job_id}")
        return

    # Show last N lines
    with error_log.open() as f:
        lines = f.readlines()
        for line in lines[-tail:]:
            click.echo(line.rstrip())


@slurm.command()
@click.argument("job_id")
@click.option("--worker", default=None, help="Specific worker ID")
@click.option("--tail", default=50, help="Number of lines to show")
@click.pass_context
def logs(ctx: click.Context, job_id: str, worker: str | None, tail: int) -> None:
    """View logs from a SLURM job."""
    # Create JobDB instance for this command
    from dr_exp.core.job_db import JobDB

    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    if worker:
        # Specific worker log
        log_file = job_db.logs_dir / f"slurm_{job_id}" / f"{worker}.log"
    else:
        # Launcher log
        log_file = job_db.logs_dir / f"slurm_{job_id}" / "launcher.log"

    if not log_file.exists():
        click.echo(f"Log file not found: {log_file}")
        return

    # Show last N lines
    with log_file.open() as f:
        lines = f.readlines()
        for line in lines[-tail:]:
            click.echo(line.rstrip())
