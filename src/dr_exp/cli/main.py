"""Main CLI entry point for dr_exp."""

import sys
from pathlib import Path
from typing import Optional

import click

from ..core.job_db import JobDB
from ..worker.base import Worker
from ..sync.queue import SyncItem


@click.group()
@click.option("--base-path", required=True, help="Base path for experiments")
@click.option("--experiment", required=True, help="Experiment name")
@click.pass_context
def cli(ctx: click.Context, base_path: str, experiment: str) -> None:
    """dr_exp - ML experiment manager."""
    # Store JobDB config in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["base_path"] = base_path
    ctx.obj["experiment"] = experiment


@cli.command()
@click.option("--worker-id", required=True, help="Unique worker ID")
@click.option("--working-dir", help="Working directory for job execution")
@click.option("--max-jobs", type=int, help="Maximum jobs to run")
@click.option("--no-sync", is_flag=True, help="Disable background sync")
@click.pass_context
def worker(
    ctx: click.Context,
    worker_id: str,
    working_dir: Optional[str],
    max_jobs: Optional[int],
    no_sync: bool,
) -> None:
    """Run a worker to process jobs."""
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    # Create worker
    worker_instance = Worker(
        job_db=job_db,
        worker_id=worker_id,
        working_dir=working_dir,
        sync_enabled=not no_sync,
    )

    # Simple sync function that just prints
    def print_sync(item: SyncItem) -> None:
        print(f"[SYNC] Would upload: {item.file_type} - {Path(item.file_path).name}")

    worker_instance.sync_fn = print_sync

    # Run worker
    print(f"Starting worker {worker_id}")
    print(f"Experiment: {ctx.obj['experiment']} at {ctx.obj['base_path']}")
    print(f"Sync: {'disabled' if no_sync else 'enabled'}")
    print("-" * 60)

    stats = worker_instance.run(max_jobs=max_jobs)

    print("-" * 60)
    print(f"Worker completed: {stats}")

    # Exit with error if any jobs failed
    if stats["failed"] > 0:
        sys.exit(1)


@cli.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--priority", type=int, default=100, help="Job priority (0-1000)")
@click.pass_context
def submit(ctx: click.Context, config_file: str, priority: int) -> None:
    """Submit a job from a config file."""
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    # Load config file
    config_path = Path(config_file)

    if config_path.suffix == ".yaml":
        import yaml

        with open(config_path) as f:
            config = yaml.safe_load(f)
    elif config_path.suffix == ".json":
        import json

        with open(config_path) as f:
            config = json.load(f)
    else:
        click.echo(f"Error: Unsupported config format: {config_path.suffix}", err=True)
        sys.exit(1)

    # Validate config
    if "_target_" not in config:
        click.echo("Error: Config must contain '_target_' field", err=True)
        sys.exit(1)

    # Create job
    try:
        job_id = job_db.create_job(config, priority=priority)
        click.echo(f"Created job: {job_id}")
        click.echo(f"Priority: {priority}")
        click.echo(f"Target: {config['_target_']}")
    except Exception as e:
        click.echo(f"Error creating job: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--status", help="Filter by status (queued, running, completed, failed)")
@click.pass_context
def list(ctx: click.Context, status: Optional[str]) -> None:
    """List jobs in the experiment."""
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    # Get jobs
    jobs = job_db.list_jobs(status=status)

    if not jobs:
        click.echo("No jobs found")
        return

    # Display header
    click.echo(f"{'ID':>36} {'Status':>10} {'Priority':>8} {'Worker':>15} {'Created'}")
    click.echo("-" * 90)

    # Display jobs
    for job in jobs:
        job_id = job["id"]
        job_status = job["status"]
        priority = job.get("priority", 0)
        worker = job.get("worker_id") or "-"
        created_at = job.get("created_at", "-")
        created = created_at[:19] if created_at != "-" else "-"  # Trim to date/time

        # Color status
        if job_status == "completed":
            status_str = click.style(f"{job_status:>10}", fg="green")
        elif job_status == "failed":
            status_str = click.style(f"{job_status:>10}", fg="red")
        elif job_status == "running":
            status_str = click.style(f"{job_status:>10}", fg="yellow")
        else:
            status_str = f"{job_status:>10}"

        click.echo(f"{job_id:>36} {status_str} {priority:>8} {worker:>15} {created}")

    # Summary
    click.echo("-" * 90)
    click.echo(f"Total: {len(jobs)} jobs")


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize a new experiment."""

    click.echo(f"Initializing experiment: {ctx.obj['experiment']}")
    click.echo(f"Base path: {ctx.obj['base_path']}")

    # Check if already exists
    exp_path = Path(ctx.obj["base_path"]) / ctx.obj["experiment"]
    if (exp_path / "jobs").exists():
        click.echo("Experiment already initialized")
        return

    # Create directory structure
    dirs = ["jobs", "storage", "sync_queue", "logs", "control"]
    for dir_name in dirs:
        dir_path = exp_path / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
        click.echo(f"Created: {dir_path}")

    # Create example config
    example_config = exp_path / "example_config.yaml"
    example_config.write_text("""# Example job configuration
_target_: src.dr_exp.trainers.test_trainer.train

# Training parameters
epochs: 10
batch_size: 32

# Model parameters
model:
  name: resnet18
  num_classes: 10

# Optimizer parameters
optimizer:
  lr: 0.001
  weight_decay: 0.0001
""")
    click.echo(f"Created: {example_config}")

    click.echo("\nExperiment initialized successfully!")
    click.echo(
        f"\nTo submit a job: dr_exp --base-path {ctx.obj['base_path']} "
        f"--experiment {ctx.obj['experiment']} submit example_config.yaml"
    )


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show experiment status."""
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    # Get experiment info
    info = job_db.get_experiment_info()

    click.echo(f"Experiment: {info['experiment_name']}")
    click.echo(f"Path: {info['experiment_path']}")
    click.echo(f"Created: {info.get('created_at', 'Unknown')}")
    click.echo()

    # Job counts
    click.echo("Job Status:")
    for status, count in sorted(info["status_counts"].items()):
        # Color based on status
        if status == "completed":
            status_str = click.style(status, fg="green")
        elif status == "failed":
            status_str = click.style(status, fg="red")
        elif status == "running":
            status_str = click.style(status, fg="yellow")
        else:
            status_str = status

        click.echo(f"  {status_str:>12}: {count}")

    click.echo(f"  {'Total':>12}: {info['total_jobs']}")

    # Check sync queue
    sync_queue_path = Path(info["experiment_path"]) / "sync_queue"
    if sync_queue_path.exists():
        from ..sync.queue import SyncQueue

        sync_queue = SyncQueue(sync_queue_path)
        sync_stats = sync_queue.get_stats()

        if sync_stats["total"] > 0:
            click.echo()
            click.echo("Sync Queue:")
            click.echo(f"  Pending: {sync_stats['pending']}")
            click.echo(f"  Failed: {sync_stats['failed']}")
            click.echo(f"  Completed: {sync_stats['completed']}")


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
