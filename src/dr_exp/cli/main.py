"""Main CLI entry point for dr_exp."""

import importlib
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, cast

import click

from ..core.job_db import JobDB
from ..sync.queue import SyncItem, SyncQueue
from ..worker.base import Worker


@click.group()
@click.option("--base-path", required=True, help="Base path for experiments")
@click.option("--experiment", required=True, help="Experiment name")
@click.pass_context
def cli(ctx: click.Context, base_path: str, experiment: str) -> None:
    """dr_exp - ML experiment manager.

    Example:
        dr_exp --base-path ./experiments --experiment my_exp submit --config-name train
    """
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
        experiment_path=str(job_db.experiment_path),
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
@click.option("--config-path", default="configs", help="Path to config directory")
@click.option(
    "--config-name", required=True, help="Name of config file (without .yaml)"
)
@click.option("--priority", default=100, help="Job priority (0-1000)")
@click.option("--tag", help="Job tag")
@click.option("--overrides", help="Hydra overrides (key=value,key2=value2)")
@click.pass_context
def submit(
    ctx: click.Context,
    config_path: str,
    config_name: str,
    priority: int,
    tag: Optional[str],
    overrides: Optional[str],
) -> None:
    """Submit a job using Hydra config composition."""
    from hydra import compose, initialize_config_dir
    from hydra.core.global_hydra import GlobalHydra
    from omegaconf import OmegaConf
    import os

    # Clear any existing Hydra instance
    GlobalHydra.instance().clear()

    # Convert config path to absolute
    if not os.path.isabs(config_path):
        config_path = os.path.abspath(config_path)

    # Prepare overrides list
    override_list = []
    if overrides:
        override_list = [o.strip() for o in overrides.split(",")]

    try:
        # Initialize Hydra with config path
        with initialize_config_dir(config_dir=config_path, version_base="1.3"):
            # Compose configuration
            cfg = compose(config_name=config_name, overrides=override_list)

            # Convert to plain dict for storage
            config_dict = OmegaConf.to_container(cfg, resolve=True)
            assert isinstance(config_dict, dict), "Config must be a dictionary"
            config_dict = cast(Dict[str, Any], config_dict)
    except Exception as e:
        click.echo(f"Error composing config: {e}", err=True)
        ctx.exit(1)

    # Validate _target_ exists
    if "_target_" not in config_dict:
        click.echo("Error: Config must contain '_target_' field", err=True)
        ctx.exit(1)

    # Validate target is importable
    target = config_dict["_target_"]
    module_path = target.rsplit(".", 1)[0]
    try:
        importlib.import_module(module_path)
    except ImportError as e:
        click.echo(f"Error: Cannot import target module {module_path}: {e}", err=True)
        ctx.exit(1)

    # Create job
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )
    job_id = job_db.create_job(
        config=config_dict,
        priority=priority,
    )

    click.echo(f"Created job: {job_id}")
    click.echo(f"Priority: {priority}")
    click.echo(f"Target: {target}")


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
        f"\nTo submit a job: dr_exp --base-path {ctx.obj['base_path']} --experiment {ctx.obj['experiment']} submit --config-path configs --config-name your_config"
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


@cli.command()
@click.argument("job_ids", nargs=-1, required=True)
@click.pass_context
def kill(ctx: click.Context, job_ids: Tuple[str, ...]) -> None:
    """Kill one or more jobs."""
    # Create JobDB instance for this command
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    killed = 0
    for job_id in job_ids:
        # Support partial job IDs
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

            # Handle different job states
            if job["status"] in ["queued", "running"]:
                # For queued jobs, we need to use fail_job directly
                if job["status"] == "queued":
                    success = job_db.fail_job(
                        full_job_id, "Killed: User requested kill"
                    )
                else:
                    # For running jobs, use mark_job_failed
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


@cli.command()
@click.argument("job_ids", nargs=-1, required=True)
@click.option("--priority", type=int, required=True, help="New priority (0-1000)")
@click.pass_context
def boost(ctx: click.Context, job_ids: Tuple[str, ...], priority: int) -> None:
    """Boost priority of one or more jobs."""
    # Create JobDB instance for this command
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    boosted = 0
    for job_id in job_ids:
        # Support partial job IDs
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

            # boost_priority expects a list
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


@cli.command()
@click.option(
    "--threshold", type=int, default=300, help="Seconds before considering job stale"
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be recovered without doing it"
)
@click.pass_context
def recover(ctx: click.Context, threshold: int, dry_run: bool) -> None:
    """Recover stale jobs that have stopped heartbeating."""
    # Create JobDB instance for this command
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    if dry_run:
        # Get stale jobs manually
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


@cli.command()
@click.option("--verbose", is_flag=True, help="Show detailed sync information")
@click.pass_context
def sync_status(ctx: click.Context, verbose: bool) -> None:
    """Show sync queue status."""

    sync_queue_path = Path(ctx.obj["base_path"]) / ctx.obj["experiment"] / "sync_queue"
    if not sync_queue_path.exists():
        click.echo("No sync queue found")
        return

    sync_queue = SyncQueue(sync_queue_path)
    stats = sync_queue.get_stats()

    # Display summary
    click.echo("Sync Queue Status:")
    click.echo(f"  Pending:   {stats['pending']}")
    click.echo(f"  Failed:    {stats['failed']}")
    click.echo(f"  Completed: {stats['completed']}")
    click.echo(f"  Total:     {stats['total']}")

    if verbose and stats["pending"] > 0:
        click.echo("\nPending items:")
        items = sync_queue.get_pending_items(limit=20)

        for item in items:
            file_name = Path(item.file_path).name
            click.echo(f"  {item.id}")
            click.echo(f"    File: {file_name} ({item.file_type})")
            click.echo(f"    Job: {item.job_id}")
            click.echo(f"    Attempts: {item.attempts}")
            if item.error:
                click.echo(f"    Last error: {item.error}")


@cli.command()
@click.argument("job_id")
@click.option("--no-sync", is_flag=True, help="Disable sync for debugging")
@click.option("--working-dir", help="Working directory for execution")
@click.pass_context
def run_one(
    ctx: click.Context, job_id: str, no_sync: bool, working_dir: Optional[str]
) -> None:
    """Run a specific job immediately by job ID.

    Example:
        dr_exp --base-path ./exp --experiment test run-one 7c9a0e51-5a7a-4d46-a7f2
    """
    # Create JobDB instance for this command
    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    # Find the job
    matching_jobs = [j for j in job_db.list_jobs() if j["id"].startswith(job_id)]

    if len(matching_jobs) == 0:
        click.echo(f"No job found matching: {job_id}", err=True)
        sys.exit(1)
    elif len(matching_jobs) > 1:
        click.echo(f"Multiple jobs match '{job_id}':", err=True)
        for job in matching_jobs:
            click.echo(f"  {job['id']}", err=True)
        sys.exit(1)

    full_job_id = matching_jobs[0]["id"]
    job = matching_jobs[0]

    # Check job status
    if job["status"] not in ["queued", "failed"]:
        click.echo(
            f"Job {full_job_id} is {job['status']} (must be queued or failed)", err=True
        )
        sys.exit(1)

    # Reserve job for special worker
    worker_id = f"run_one_{int(time.time())}"
    if not job_db.reserve_job(full_job_id, worker_id):
        click.echo(f"Failed to reserve job {full_job_id}", err=True)
        sys.exit(1)

    click.echo(f"Running job: {full_job_id}")
    click.echo(f"Target: {job['config']['_target_']}")
    click.echo(f"Priority: {job.get('priority', 0)}")
    click.echo("-" * 60)

    # Create worker
    worker = Worker(
        job_db=job_db,
        worker_id=worker_id,
        working_dir=working_dir,
        experiment_path=str(job_db.experiment_path),
        sync_enabled=not no_sync,
    )

    # Simple sync function
    def print_sync(item: SyncItem) -> None:
        print(f"[SYNC] Would upload: {item.file_type} - {Path(item.file_path).name}")

    worker.sync_fn = print_sync

    # Claim and run the reserved job
    claimed_job = job_db.claim_reserved_job(full_job_id, worker_id)
    if not claimed_job:
        click.echo(f"Failed to claim reserved job {full_job_id}", err=True)
        sys.exit(1)

    # Execute directly
    worker.current_job_id = claimed_job["id"]
    result = worker.execute_job(claimed_job)

    # Update job status
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
def validate(ctx: click.Context) -> None:
    """Validate experiment setup and configuration."""
    exp_path = Path(ctx.obj["base_path"]) / ctx.obj["experiment"]

    # Try to create JobDB to validate initialization
    try:
        job_db = JobDB(
            base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
        )
    except RuntimeError as e:
        # Experiment not initialized
        click.echo(click.style("✗ Validation FAILED", fg="red", bold=True))
        click.echo("\nIssues found:")
        click.echo(f"  ✗ {e}")
        sys.exit(1)

    issues = []
    warnings = []

    # Check directory structure
    required_dirs = ["jobs", "storage", "sync_queue"]
    for dir_name in required_dirs:
        dir_path = exp_path / dir_name
        if not dir_path.exists():
            issues.append(f"Missing directory: {dir_path}")
        elif not dir_path.is_dir():
            issues.append(f"Not a directory: {dir_path}")
        elif not os.access(dir_path, os.W_OK):
            issues.append(f"Not writable: {dir_path}")

    # Check for jobs
    try:
        jobs = job_db.list_jobs()
        if len(jobs) == 0:
            warnings.append("No jobs found in experiment")
        else:
            # Check job health
            running_jobs = [j for j in jobs if j["status"] == "running"]
            if running_jobs:
                now = datetime.now(UTC)

                for job in running_jobs:
                    last_heartbeat = job.get("last_heartbeat")
                    if last_heartbeat:
                        last_time = datetime.fromisoformat(last_heartbeat)
                        stale_seconds = (now - last_time).total_seconds()
                        if stale_seconds > 300:
                            warnings.append(
                                f"Job {job['id']} may be stale (no heartbeat for {int(stale_seconds)}s)"
                            )
    except Exception as e:
        issues.append(f"Error reading jobs: {e}")

    # Display results
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

    # Show summary
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
