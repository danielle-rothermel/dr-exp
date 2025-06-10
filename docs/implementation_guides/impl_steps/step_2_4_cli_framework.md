# Step 2.4: CLI Framework

## Goal (1 sentence)
Create a basic CLI structure with worker run and job submit commands using Click.

## Prerequisites
- [ ] Step 2.3 completed and validated
- [ ] Required files exist: Worker with threading support
- [ ] Click installed: `uv add click`

## Implementation

### 1. Create src/dr_exp/cli/__init__.py
```python
# Empty file to make this a package
```

### 2. Create src/dr_exp/cli/main.py
```python
"""Main CLI entry point for dr_exp."""
import sys
from pathlib import Path
from typing import Optional

import click

from ..core.job_db import JobDB
from ..worker.base import Worker


@click.group()
@click.option('--base-path', required=True, help='Base path for experiments')
@click.option('--experiment', required=True, help='Experiment name')
@click.pass_context
def cli(ctx, base_path: str, experiment: str):
    """dr_exp - ML experiment manager."""
    # Store JobDB in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj['job_db'] = JobDB(base_path=base_path, experiment_name=experiment)
    ctx.obj['base_path'] = base_path
    ctx.obj['experiment'] = experiment


@cli.command()
@click.option('--worker-id', required=True, help='Unique worker ID')
@click.option('--working-dir', help='Working directory for job execution')
@click.option('--max-jobs', type=int, help='Maximum jobs to run')
@click.option('--no-sync', is_flag=True, help='Disable background sync')
@click.pass_context
def worker(ctx, worker_id: str, working_dir: Optional[str], 
           max_jobs: Optional[int], no_sync: bool):
    """Run a worker to process jobs."""
    job_db = ctx.obj['job_db']
    
    # Create worker
    worker_instance = Worker(
        job_db=job_db,
        worker_id=worker_id,
        working_dir=working_dir,
        sync_enabled=not no_sync
    )
    
    # Simple sync function that just prints
    def print_sync(item):
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
    if stats['failed'] > 0:
        sys.exit(1)


@cli.command()
@click.argument('config_file', type=click.Path(exists=True))
@click.option('--priority', type=int, default=100, help='Job priority (0-1000)')
@click.pass_context
def submit(ctx, config_file: str, priority: int):
    """Submit a job from a config file."""
    job_db = ctx.obj['job_db']
    
    # Load config file
    config_path = Path(config_file)
    
    if config_path.suffix == '.yaml':
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)
    elif config_path.suffix == '.json':
        import json
        with open(config_path) as f:
            config = json.load(f)
    else:
        click.echo(f"Error: Unsupported config format: {config_path.suffix}", err=True)
        sys.exit(1)
    
    # Validate config
    if '_target_' not in config:
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
@click.option('--status', help='Filter by status (queued, running, completed, failed)')
@click.pass_context
def list(ctx, status: Optional[str]):
    """List jobs in the experiment."""
    job_db = ctx.obj['job_db']
    
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
        job_id = job['id']
        job_status = job['status']
        priority = job.get('priority', 0)
        worker = job.get('worker_id', '-')
        created = job.get('created_at', '-')[:19]  # Trim to date/time
        
        # Color status
        if job_status == 'completed':
            status_str = click.style(f"{job_status:>10}", fg='green')
        elif job_status == 'failed':
            status_str = click.style(f"{job_status:>10}", fg='red')
        elif job_status == 'running':
            status_str = click.style(f"{job_status:>10}", fg='yellow')
        else:
            status_str = f"{job_status:>10}"
        
        click.echo(f"{job_id:>36} {status_str} {priority:>8} {worker:>15} {created}")
    
    # Summary
    click.echo("-" * 90)
    click.echo(f"Total: {len(jobs)} jobs")


@cli.command()
@click.pass_context
def init(ctx):
    """Initialize a new experiment."""
    job_db = ctx.obj['job_db']
    
    click.echo(f"Initializing experiment: {ctx.obj['experiment']}")
    click.echo(f"Base path: {ctx.obj['base_path']}")
    
    # Check if already exists
    exp_path = Path(ctx.obj['base_path']) / ctx.obj['experiment']
    if (exp_path / 'jobs').exists():
        click.echo("Experiment already initialized")
        return
    
    # Create directory structure
    dirs = ['jobs', 'storage', 'sync_queue']
    for dir_name in dirs:
        dir_path = exp_path / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
        click.echo(f"Created: {dir_path}")
    
    # Create example config
    example_config = exp_path / 'example_config.yaml'
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
    click.echo(f"\nTo submit a job: dr_exp --base-path {ctx.obj['base_path']} "
               f"--experiment {ctx.obj['experiment']} submit example_config.yaml")


@cli.command()
@click.pass_context
def status(ctx):
    """Show experiment status."""
    job_db = ctx.obj['job_db']
    
    # Get experiment info
    info = job_db.get_experiment_info()
    
    click.echo(f"Experiment: {info['experiment_name']}")
    click.echo(f"Path: {info['experiment_path']}")
    click.echo(f"Created: {info.get('created_at', 'Unknown')}")
    click.echo()
    
    # Job counts
    click.echo("Job Status:")
    for status, count in sorted(info['status_counts'].items()):
        # Color based on status
        if status == 'completed':
            status_str = click.style(status, fg='green')
        elif status == 'failed':
            status_str = click.style(status, fg='red')
        elif status == 'running':
            status_str = click.style(status, fg='yellow')
        else:
            status_str = status
        
        click.echo(f"  {status_str:>12}: {count}")
    
    click.echo(f"  {'Total':>12}: {info['total_jobs']}")
    
    # Check sync queue
    sync_queue_path = Path(info['experiment_path']) / 'sync_queue'
    if sync_queue_path.exists():
        from ..sync.queue import SyncQueue
        sync_queue = SyncQueue(sync_queue_path)
        sync_stats = sync_queue.get_stats()
        
        if sync_stats['total'] > 0:
            click.echo()
            click.echo("Sync Queue:")
            click.echo(f"  Pending: {sync_stats['pending']}")
            click.echo(f"  Failed: {sync_stats['failed']}")
            click.echo(f"  Completed: {sync_stats['completed']}")


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()
```

### 3. Create configs/test_job.yaml
```yaml
# Test job configuration
_target_: src.dr_exp.trainers.test_trainer.train

# Training parameters
epochs: 5
batch_size: 32

# Test parameters
fail_rate: 0.0  # Set to 0.0-1.0 to test failures
```

### 4. Create tests/implementation/test_step_2_4.py
```python
"""Test CLI functionality."""
import tempfile
import json
import pytest
from pathlib import Path
from click.testing import CliRunner

from src.dr_exp.cli.main import cli
from src.dr_exp.core.job_db import JobDB


def test_cli_init():
    """Test experiment initialization."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'init'
        ])
        
        assert result.exit_code == 0
        assert 'Experiment initialized successfully' in result.output
        
        # Verify directories created
        exp_path = Path(tmpdir) / 'test_exp'
        assert (exp_path / 'jobs').exists()
        assert (exp_path / 'storage').exists()
        assert (exp_path / 'sync_queue').exists()
        assert (exp_path / 'example_config.yaml').exists()
        


def test_cli_submit():
    """Test job submission."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize experiment
        runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'init'
        ])
        
        # Create config file
        config_file = Path(tmpdir) / 'test_config.yaml'
        config_file.write_text("""
_target_: src.dr_exp.trainers.test_trainer.train
epochs: 10
""")
        
        # Submit job
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'submit', str(config_file),
            '--priority', '500'
        ])
        
        assert result.exit_code == 0
        assert 'Created job:' in result.output
        assert 'Priority: 500' in result.output
        
        # Verify job created
        job_db = JobDB(base_path=tmpdir, experiment_name='test_exp')
        jobs = job_db.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]['priority'] == 500
        


def test_cli_list():
    """Test job listing."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some jobs directly
        job_db = JobDB(base_path=tmpdir, experiment_name='test_exp')
        
        # Various job states
        config = {'_target_': 'test.train'}
        job1 = job_db.create_job(config, priority=100)
        job2 = job_db.create_job(config, priority=500)
        job3 = job_db.create_job(config, priority=900)
        
        # Claim and complete one
        job_db.claim_next_job('worker1')
        job_db.complete_job(job3)
        
        # List all jobs
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'list'
        ])
        
        assert result.exit_code == 0
        assert 'Total: 3 jobs' in result.output
        assert job1 in result.output
        assert job2 in result.output
        assert job3 in result.output
        
        # List only queued
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'list',
            '--status', 'queued'
        ])
        
        assert result.exit_code == 0
        assert 'Total: 2 jobs' in result.output
        assert job1 in result.output
        assert job2 in result.output
        assert job3 not in result.output
        


def test_cli_status():
    """Test experiment status."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create experiment with various jobs
        job_db = JobDB(base_path=tmpdir, experiment_name='test_exp')
        
        config = {'_target_': 'test.train'}
        
        # Create jobs in different states
        for _ in range(3):
            job_db.create_job(config)
        
        for i in range(2):
            job_id = job_db.create_job(config)
            job_db.claim_next_job(f'worker{i}')
            if i == 0:
                job_db.complete_job(job_id)
            else:
                job_db.fail_job(job_id, 'Test error')
        
        # Get status
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'status'
        ])
        
        assert result.exit_code == 0
        assert 'Experiment: test_exp' in result.output
        assert 'Job Status:' in result.output
        assert 'queued: 3' in result.output
        assert 'completed: 1' in result.output
        assert 'failed: 1' in result.output
        assert 'Total: 5' in result.output
        


def test_cli_worker():
    """Test running a worker via CLI."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a job
        job_db = JobDB(base_path=tmpdir, experiment_name='test_exp')
        config = {'_target_': 'src.dr_exp.trainers.test_trainer.train', 'epochs': 2}
        job_db.create_job(config)
        
        # Run worker
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'worker',
            '--worker-id', 'cli_worker',
            '--max-jobs', '1',
            '--no-sync'  # Disable sync for testing
        ])
        
        assert result.exit_code == 0
        assert 'Starting worker cli_worker' in result.output
        assert 'Worker completed:' in result.output
        assert "'completed': 1" in result.output
        


def test_cli_worker_with_sync():
    """Test worker with sync enabled."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a job
        job_db = JobDB(base_path=tmpdir, experiment_name='test_exp')
        config = {'_target_': 'src.dr_exp.trainers.test_trainer.train', 'epochs': 2}
        job_db.create_job(config)
        
        # Run worker with sync
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'worker',
            '--worker-id', 'sync_worker',
            '--max-jobs', '1'
        ])
        
        assert result.exit_code == 0
        assert 'Sync: enabled' in result.output
        assert '[SYNC] Would upload:' in result.output  # Our mock sync function
        


def test_cli_error_handling():
    """Test CLI error handling."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Try to submit without _target_
        bad_config = Path(tmpdir) / 'bad_config.json'
        bad_config.write_text('{"epochs": 10}')
        
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'submit', str(bad_config)
        ])
        
        assert result.exit_code == 1
        assert "Config must contain '_target_'" in result.output
        
        # Try to submit non-existent file
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'submit', 'nonexistent.yaml'
        ])
        
        assert result.exit_code == 2  # Click file not found
        


```

### 5. Create setup.py (for CLI entry point)
```python
"""Setup for dr_exp CLI."""
from setuptools import setup, find_packages

setup(
    name="dr_exp",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "click",
        "hydra-core",
        "omegaconf",
        "pyyaml",
    ],
    entry_points={
        "console_scripts": [
            "dr_exp=dr_exp.cli.main:main",
        ],
    },
)
```

## Validation
```bash
# Install dependencies
uv add click pyyaml

# Install package in development mode
uv pip install -e .

# Run the test with pytest
pt tests/implementation/test_step_2_4.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_2_4.py::test_cli_init PASSED
# tests/implementation/test_step_2_4.py::test_cli_submit PASSED
# tests/implementation/test_step_2_4.py::test_cli_list PASSED
# tests/implementation/test_step_2_4.py::test_cli_status PASSED
# tests/implementation/test_step_2_4.py::test_cli_worker PASSED
# tests/implementation/test_step_2_4.py::test_cli_worker_with_sync PASSED
# tests/implementation/test_step_2_4.py::test_cli_error_handling PASSED
# ============================== 7 passed in X.XXs ===============================

# Test the actual CLI
dr_exp --help

# Initialize an experiment
dr_exp --base-path /tmp/test --experiment my_exp init

# Submit a job
dr_exp --base-path /tmp/test --experiment my_exp submit configs/test_job.yaml

# List jobs
dr_exp --base-path /tmp/test --experiment my_exp list

# Run code quality checks
ckdr
```

## Common Mistakes
- DO NOT: Use argparse - Click is simpler and more powerful
- DO NOT: Add complex command structures - keep it flat and simple
- DO NOT: Forget to pass context between commands
- DO NOT: Mix business logic with CLI code - keep it thin
- DO NOT: Add interactive prompts - all parameters via flags/options

## Next Step
Proceed to Step 2.5: Job Management Commands