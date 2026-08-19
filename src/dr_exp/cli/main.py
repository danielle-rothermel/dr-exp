"""Main CLI entry point for dr_exp."""

import importlib
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import click

from dr_exp.core.job_db import JobDB
from dr_exp.worker.base import Worker
from .commands.slurm import slurm
from .commands.sweep import sweep

DESCRIPTION_MAX_LENGTH = 30
DESCRIPTION_TRUNCATE_LENGTH = 27
STALE_JOB_THRESHOLD_SECONDS = 300


@click.group()
@click.option("--base-path", required=True, help="Base path for experiments")
@click.option("--experiment", required=True, help="Experiment name")
@click.pass_context
def cli(ctx: click.Context, base_path: str, experiment: str) -> None:
    """dr_exp - ML experiment manager."""
    ctx.ensure_object(dict)
    ctx.obj["base_path"] = base_path
    ctx.obj["experiment"] = experiment


@cli.command()
@click.option("--worker-id", required=True, help="Unique worker ID")
@click.option("--working-dir", help="Working directory for job execution")
@click.option("--max-jobs", type=int, help="Maximum jobs to run")
@click.pass_context
def worker(
    ctx: click.Context,
    worker_id: str,
    working_dir: str | None,
    max_jobs: int | None,
) -> None:
    """Run a worker to process jobs."""
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    worker_instance = Worker(
        job_db=job_db,
        worker_id=worker_id,
        working_dir=working_dir,
    )

    print(f"Starting worker {worker_id}")
    print(f"Experiment: {ctx.obj['experiment']} at {ctx.obj['base_path']}")
    print("-" * 60)

    stats = worker_instance.run(max_jobs=max_jobs)

    print("-" * 60)
    print(f"Worker completed: {stats}")

    if stats["failed"] > 0:
        sys.exit(1)


@cli.group()
@click.pass_context
def system(ctx: click.Context) -> None:
    """System and launcher commands."""


@system.command()
@click.option("--workers-per-gpu", default=2, help="Workers per GPU")
@click.option("--max-hours", default=47, help="Maximum runtime in hours")
@click.pass_context
def launcher(ctx: click.Context, workers_per_gpu: int, max_hours: float) -> None:
    """Run multi-worker launcher for SLURM jobs."""
    from dr_exp.worker.launcher import WorkerLauncher

    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )
    experiment_name = ctx.obj["experiment"]
    log_dir = job_db.logs_dir

    launcher_instance = WorkerLauncher(
        job_db=job_db,
        experiment_name=experiment_name,
        base_log_dir=log_dir,
        workers_per_gpu=workers_per_gpu,
        max_runtime_hours=max_hours,
    )

    launcher_instance.run()


@cli.group()
@click.pass_context
def job(ctx: click.Context) -> None:
    """Job management commands."""


job.add_command(sweep)
cli.add_command(slurm)


@job.command()
@click.option("--config-path", default="configs", help="Path to config directory")
@click.option(
    "--config-name", required=True, help="Name of config file (without .yaml)"
)
@click.option("--priority", default=100, help="Job priority (0-1000)")
@click.option(
    "--tags", help="Comma-separated job tags (e.g., 'baseline,gpu-test,ablation')"
)
@click.option("--overrides", help="Hydra overrides (key=value,key2=value2)")
@click.pass_context
def submit(
    ctx: click.Context,
    config_path: str,
    config_name: str,
    priority: int,
    tags: str | None,
    overrides: str | None,
) -> None:
    """Submit a job using Hydra config composition."""
    from hydra import compose, initialize_config_dir
    from hydra.core.global_hydra import GlobalHydra
    from omegaconf import OmegaConf

    GlobalHydra.instance().clear()

    config_path_obj = Path(config_path)
    if not config_path_obj.is_absolute():
        config_path = str(config_path_obj.resolve())

    override_list = []
    if overrides:
        override_list = [o.strip() for o in overrides.split(",")]

    try:
        with initialize_config_dir(config_dir=config_path, version_base="1.3"):
            cfg = compose(config_name=config_name, overrides=override_list)
            config_dict = OmegaConf.to_container(cfg, resolve=True)
            assert isinstance(config_dict, dict), "Config must be a dictionary"
            config_dict = cast(dict[str, Any], config_dict)
    except Exception as e:
        click.echo(f"Error composing config: {e}", err=True)
        ctx.exit(1)

    if "_target_" not in config_dict:
        click.echo("Error: Config must contain '_target_' field", err=True)
        ctx.exit(1)

    target = config_dict["_target_"]
    module_path = target.rsplit(".", 1)[0]
    try:
        importlib.import_module(module_path)
    except ImportError as e:
        click.echo(f"Error: Cannot import target module {module_path}: {e}", err=True)
        ctx.exit(1)

    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )
    job_id = job_db.create_job(
        config=config_dict,
        priority=priority,
        tags=tag_list,
    )

    click.echo(f"Created job: {job_id}")
    click.echo(f"Priority: {priority}")
    click.echo(f"Target: {target}")
    if tag_list:
        click.echo(f"Tags: {', '.join(tag_list)}")


@job.command(name="list")
@click.option("--status", help="Filter by status (queued, running, completed, failed)")
@click.option("--tag", help="Filter by tag")
@click.pass_context
def list_jobs(ctx: click.Context, status: str | None, tag: str | None) -> None:
    """List jobs in the experiment."""
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    jobs = job_db.list_jobs(status=status)

    if tag:
        jobs = [job for job in jobs if tag in job.get("tags", [])]

    if not jobs:
        click.echo("No jobs found")
        return

    header = (
        f"{'ID':>12} {'Description':>30} {'Status':>10} {'Priority':>8} "
        f"{'Worker':>15} {'Created'}"
    )
    click.echo(header)
    click.echo("-" * 105)

    for job in jobs:
        job_id = job["id"][:12]
        job_status = job["status"]
        priority = job.get("priority", 0)
        worker = job.get("worker_id") or "-"
        created_at = job.get("created_at", "-")
        created = created_at[:19] if created_at != "-" else "-"

        config = job.get("config", {})
        run_name = config.get("run_name", "unknown")
        seed = config.get("seed", "?")
        job_tags = job.get("tags", [])

        description = f"{run_name}/seed_{seed}"
        if job_tags:
            description += f" [{','.join(job_tags)}]"

        if len(description) > DESCRIPTION_MAX_LENGTH:
            description = description[:DESCRIPTION_TRUNCATE_LENGTH] + "..."

        if job_status == "completed":
            status_str = click.style(f"{job_status:>10}", fg="green")
        elif job_status == "failed":
            status_str = click.style(f"{job_status:>10}", fg="red")
        elif job_status == "running":
            status_str = click.style(f"{job_status:>10}", fg="yellow")
        else:
            status_str = f"{job_status:>10}"

        job_line = (
            f"{job_id:>12} {description:>30} {status_str} {priority:>8} "
            f"{worker:>15} {created}"
        )
        click.echo(job_line)

    click.echo("-" * 105)
    click.echo(f"Total: {len(jobs)} jobs")


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize a new experiment."""
    click.echo(f"Initializing experiment: {ctx.obj['experiment']}")
    click.echo(f"Base path: {ctx.obj['base_path']}")

    exp_path = Path(ctx.obj["base_path"]) / ctx.obj["experiment"]
    if (exp_path / "jobs").exists():
        click.echo("Experiment already initialized")
        return

    dirs = ["jobs", "storage", "logs", "control"]
    for dir_name in dirs:
        dir_path = exp_path / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
        click.echo(f"Created: {dir_path}")

    example_config = exp_path / "example_config.yaml"
    example_config.write_text("""# Example job configuration
_target_: dr_exp.training.dummy_trainer.train

epochs: 10
batch_size: 32
lr: 0.001
model: resnet18
""")
    click.echo(f"Created: {example_config}")

    click.echo("\nExperiment initialized successfully!")
    submit_example = (
        f"\nTo submit a job: dr_exp --base-path {ctx.obj['base_path']} "
        f"--experiment {ctx.obj['experiment']} job submit --config-path configs "
        f"--config-name your_config"
    )
    click.echo(submit_example)


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show experiment status."""
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    info = job_db.get_experiment_info()

    click.echo(f"Experiment: {info['experiment_name']}")
    click.echo(f"Path: {info['experiment_path']}")
    click.echo(f"Created: {info.get('created_at', 'Unknown')}")
    click.echo()

    click.echo("Job Status:")
    for status_name, count in sorted(info["status_counts"].items()):
        if status_name == "completed":
            status_str = click.style(status_name, fg="green")
        elif status_name == "failed":
            status_str = click.style(status_name, fg="red")
        elif status_name == "running":
            status_str = click.style(status_name, fg="yellow")
        else:
            status_str = status_name

        click.echo(f"  {status_str:>12}: {count}")

    click.echo(f"  {'Total':>12}: {info['total_jobs']}")


@job.command()
@click.argument("job_ids", nargs=-1, required=True)
@click.pass_context
def kill(ctx: click.Context, job_ids: tuple[str, ...]) -> None:
    """Kill one or more jobs."""
    # KNOWN ISSUE (see README): only rewrites job JSON; running trainer is not signalled
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    killed = 0
    for job_id in job_ids:
        matching_jobs = [j for j in job_db.list_jobs() if j["id"].startswith(job_id)]

        if len(matching_jobs) == 0:
            click.echo(f"No job found matching: {job_id}", err=True)
        elif len(matching_jobs) > 1:
            click.echo(f"Multiple jobs match '{job_id}':", err=True)
            for job in matching_jobs:
                click.echo(f"  {job['id']}", err=True)
        else:
            full_job_id = matching_jobs[0]["id"]
            job = matching_jobs[0]

            if job["status"] in ["queued", "running"]:
                if job["status"] == "queued":
                    success = job_db.fail_job(
                        full_job_id, "Killed: User requested kill"
                    )
                else:
                    success = job_db.mark_job_failed(full_job_id, "User requested kill")

                if success:
                    click.echo(f"Killed job: {full_job_id}")
                    killed += 1
                else:
                    click.echo(f"Failed to kill job: {full_job_id}", err=True)
            else:
                click.echo(f"Job {full_job_id} is already {job['status']}", err=True)

    if killed > 0:
        click.echo(f"\nKilled {killed} job(s)")
    else:
        sys.exit(1)


@job.command()
@click.argument("job_ids", nargs=-1, required=True)
@click.option("--priority", type=int, required=True, help="New priority (0-1000)")
@click.pass_context
def boost(ctx: click.Context, job_ids: tuple[str, ...], priority: int) -> None:
    """Boost priority of one or more jobs."""
    # KNOWN ISSUE (see README): sets absolute priority despite the name
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    boosted = 0
    for job_id in job_ids:
        matching_jobs = [j for j in job_db.list_jobs() if j["id"].startswith(job_id)]

        if len(matching_jobs) == 0:
            click.echo(f"No job found matching: {job_id}", err=True)
        elif len(matching_jobs) > 1:
            click.echo(f"Multiple jobs match '{job_id}':", err=True)
            for job in matching_jobs:
                click.echo(f"  {job['id']}", err=True)
        else:
            full_job_id = matching_jobs[0]["id"]
            old_priority = matching_jobs[0].get("priority", 0)

            if job_db.boost_priority([full_job_id], priority) > 0:
                click.echo(f"Boosted job: {full_job_id} ({old_priority} → {priority})")
                boosted += 1
            else:
                click.echo(
                    f"Failed to boost job: {full_job_id} (not queued?)", err=True
                )

    if boosted > 0:
        click.echo(f"\nBoosted {boosted} job(s)")
    else:
        sys.exit(1)


@job.command()
@click.option(
    "--threshold", type=int, default=300, help="Seconds before considering job stale"
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be recovered without doing it"
)
@click.pass_context
def recover(ctx: click.Context, threshold: int, dry_run: bool) -> None:
    """Recover stale jobs that have stopped heartbeating."""
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    if dry_run:
        now = datetime.now(UTC)

        stale_jobs = []
        for job in job_db.list_jobs(status="running"):
            last_heartbeat = job.get("last_heartbeat")
            if not last_heartbeat:
                last_heartbeat = job.get("started_at")

            if last_heartbeat:
                last_time = datetime.fromisoformat(last_heartbeat)
                if (now - last_time).total_seconds() > threshold:
                    stale_jobs.append(job)

        if stale_jobs:
            click.echo(f"Would recover {len(stale_jobs)} stale job(s):")
            for job in stale_jobs:
                worker = job.get("worker_id", "unknown")
                click.echo(f"  {job['id']} (worker: {worker})")
        else:
            click.echo("No stale jobs found")
    else:
        recovered = job_db.recover_stale_jobs(threshold)

        if recovered:
            click.echo(f"Recovered {len(recovered)} stale job(s):")
            for job_id in recovered:
                click.echo(f"  {job_id}")
        else:
            click.echo("No stale jobs found")


@job.command()
@click.argument("job_id")
@click.option("--working-dir", help="Working directory for execution")
@click.pass_context
def run_one(ctx: click.Context, job_id: str, working_dir: str | None) -> None:
    """Run a specific job immediately by job ID."""
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    matching_jobs = [j for j in job_db.list_jobs() if j["id"].startswith(job_id)]

    if len(matching_jobs) == 0:
        click.echo(f"No job found matching: {job_id}", err=True)
        sys.exit(1)
    if len(matching_jobs) > 1:
        click.echo(f"Multiple jobs match '{job_id}':", err=True)
        for job in matching_jobs:
            click.echo(f"  {job['id']}", err=True)
        sys.exit(1)

    full_job_id = matching_jobs[0]["id"]
    job = matching_jobs[0]

    if job["status"] not in ["queued", "failed"]:
        click.echo(
            f"Job {full_job_id} is {job['status']} (must be queued or failed)", err=True
        )
        sys.exit(1)

    worker_id = f"run_one_{int(time.time())}"
    if not job_db.reserve_job(full_job_id, worker_id):
        click.echo(f"Failed to reserve job {full_job_id}", err=True)
        sys.exit(1)

    click.echo(f"Running job: {full_job_id}")
    click.echo(f"Target: {job['config']['_target_']}")
    click.echo(f"Priority: {job.get('priority', 0)}")
    click.echo("-" * 60)

    worker_instance = Worker(
        job_db=job_db,
        worker_id=worker_id,
        working_dir=working_dir,
    )

    claimed_job = job_db.claim_reserved_job(full_job_id, worker_id)
    if not claimed_job:
        click.echo(f"Failed to claim reserved job {full_job_id}", err=True)
        sys.exit(1)

    worker_instance.current_job_id = claimed_job["id"]
    result = worker_instance.execute_job(claimed_job)

    if result["status"] == "success":
        metrics = None
        if isinstance(result.get("result"), dict):
            metrics = result["result"].get("metrics")
        job_db.complete_job(claimed_job["id"], metrics)
        status_msg = click.style("COMPLETED", fg="green")
    else:
        job_db.fail_job(claimed_job["id"], result["error"])
        status_msg = click.style("FAILED", fg="red")

    click.echo("-" * 60)
    click.echo(f"Job {full_job_id}: {status_msg}")

    if result["status"] == "failed":
        click.echo(f"\nError: {result['error']}")
        sys.exit(1)


@cli.command()
@click.pass_context
def validate(ctx: click.Context) -> None:  # noqa: C901
    """Validate experiment setup and configuration."""
    exp_path = Path(ctx.obj["base_path"]) / ctx.obj["experiment"]

    try:
        job_db = JobDB(
            base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
        )
    except RuntimeError as e:
        click.echo(click.style("✗ Validation FAILED", fg="red", bold=True))
        click.echo("\nIssues found:")
        click.echo(f"  ✗ {e}")
        sys.exit(1)

    issues = []
    warnings = []

    required_dirs = ["jobs", "storage"]
    for dir_name in required_dirs:
        dir_path = exp_path / dir_name
        if not dir_path.exists():
            issues.append(f"Missing directory: {dir_path}")
        elif not dir_path.is_dir():
            issues.append(f"Not a directory: {dir_path}")
        elif not os.access(dir_path, os.W_OK):
            issues.append(f"Not writable: {dir_path}")

    try:
        jobs = job_db.list_jobs()
        if len(jobs) == 0:
            warnings.append("No jobs found in experiment")
        else:
            running_jobs = [j for j in jobs if j["status"] == "running"]
            if running_jobs:
                now = datetime.now(UTC)

                for job in running_jobs:
                    last_heartbeat = job.get("last_heartbeat")
                    if last_heartbeat:
                        last_time = datetime.fromisoformat(last_heartbeat)
                        stale_seconds = (now - last_time).total_seconds()
                        if stale_seconds > STALE_JOB_THRESHOLD_SECONDS:
                            stale_warning = (
                                f"Job {job['id']} may be stale "
                                f"(no heartbeat for {int(stale_seconds)}s)"
                            )
                            warnings.append(stale_warning)
    except Exception as e:
        issues.append(f"Error reading jobs: {e}")

    if issues:
        click.echo(click.style("✗ Validation FAILED", fg="red", bold=True))
        click.echo("\nIssues found:")
        for issue in issues:
            click.echo(f"  ✗ {issue}")
    else:
        click.echo(click.style("✓ Validation PASSED", fg="green", bold=True))

    if warnings:
        click.echo("\nWarnings:")
        for warning in warnings:
            click.echo(f"  ⚠ {warning}")

    info = job_db.get_experiment_info()
    click.echo(f"\nExperiment: {info['experiment_name']}")
    click.echo(f"Path: {info['experiment_path']}")
    click.echo(f"Total jobs: {info['total_jobs']}")

    sys.exit(1 if issues else 0)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
