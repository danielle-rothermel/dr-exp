# Step 2.5: Job Management Commands

## Goal (1 sentence)
Add CLI commands for killing jobs, boosting priority, recovering stale jobs, and monitoring sync status.

## Prerequisites
- [ ] Step 2.4 completed and validated  
- [ ] Required files exist: CLI framework with basic commands
- [ ] test_step_2_4.py passes

## Implementation

### 1. Update src/dr_exp/cli/main.py
Add these commands after the existing ones:
```python
@cli.command()
@click.argument('job_ids', nargs=-1, required=True)
@click.pass_context
def kill(ctx, job_ids):
    """Kill one or more jobs."""
    job_db = ctx.obj['job_db']
    
    killed = 0
    for job_id in job_ids:
        # Support partial job IDs
        matching_jobs = [j for j in job_db.list_jobs() if j['id'].startswith(job_id)]
        
        if len(matching_jobs) == 0:
            click.echo(f"No job found matching: {job_id}", err=True)
        elif len(matching_jobs) > 1:
            click.echo(f"Multiple jobs match '{job_id}':", err=True)
            for job in matching_jobs:
                click.echo(f"  {job['id']}", err=True)
        else:
            full_job_id = matching_jobs[0]['id']
            if job_db.kill_job(full_job_id):
                click.echo(f"Killed job: {full_job_id}")
                killed += 1
            else:
                click.echo(f"Failed to kill job: {full_job_id}", err=True)
    
    if killed > 0:
        click.echo(f"\nKilled {killed} job(s)")
    else:
        sys.exit(1)


@cli.command()
@click.argument('job_ids', nargs=-1, required=True)
@click.option('--priority', type=int, required=True, help='New priority (0-1000)')
@click.pass_context
def boost(ctx, job_ids, priority: int):
    """Boost priority of one or more jobs."""
    job_db = ctx.obj['job_db']
    
    boosted = 0
    for job_id in job_ids:
        # Support partial job IDs
        matching_jobs = [j for j in job_db.list_jobs() if j['id'].startswith(job_id)]
        
        if len(matching_jobs) == 0:
            click.echo(f"No job found matching: {job_id}", err=True)
        elif len(matching_jobs) > 1:
            click.echo(f"Multiple jobs match '{job_id}':", err=True)
            for job in matching_jobs:
                click.echo(f"  {job['id']}", err=True)
        else:
            full_job_id = matching_jobs[0]['id']
            old_priority = matching_jobs[0].get('priority', 0)
            
            if job_db.boost_priority(full_job_id, priority):
                click.echo(f"Boosted job: {full_job_id} ({old_priority} → {priority})")
                boosted += 1
            else:
                click.echo(f"Failed to boost job: {full_job_id} (not queued?)", err=True)
    
    if boosted > 0:
        click.echo(f"\nBoosted {boosted} job(s)")
    else:
        sys.exit(1)


@cli.command()
@click.option('--threshold', type=int, default=300, help='Seconds before considering job stale')
@click.option('--dry-run', is_flag=True, help='Show what would be recovered without doing it')
@click.pass_context
def recover(ctx, threshold: int, dry_run: bool):
    """Recover stale jobs that have stopped heartbeating."""
    job_db = ctx.obj['job_db']
    
    if dry_run:
        # Get stale jobs manually
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        
        stale_jobs = []
        for job in job_db.list_jobs(status='running'):
            last_heartbeat = job.get('last_heartbeat')
            if not last_heartbeat:
                last_heartbeat = job.get('started_at')
            
            if last_heartbeat:
                last_time = datetime.fromisoformat(last_heartbeat)
                if (now - last_time).total_seconds() > threshold:
                    stale_jobs.append(job)
        
        if stale_jobs:
            click.echo(f"Would recover {len(stale_jobs)} stale job(s):")
            for job in stale_jobs:
                worker = job.get('worker_id', 'unknown')
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
@click.option('--verbose', is_flag=True, help='Show detailed sync information')
@click.pass_context
def sync_status(ctx, verbose: bool):
    """Show sync queue status."""
    from ..sync.queue import SyncQueue
    
    sync_queue_path = Path(ctx.obj['base_path']) / ctx.obj['experiment'] / 'sync_queue'
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
    
    if verbose and stats['pending'] > 0:
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
@click.argument('job_id')
@click.option('--no-sync', is_flag=True, help='Disable sync for debugging')
@click.option('--working-dir', help='Working directory for execution')
@click.pass_context
def run_one(ctx, job_id: str, no_sync: bool, working_dir: Optional[str]):
    """Run a specific job immediately (for debugging)."""
    job_db = ctx.obj['job_db']
    
    # Find the job
    matching_jobs = [j for j in job_db.list_jobs() if j['id'].startswith(job_id)]
    
    if len(matching_jobs) == 0:
        click.echo(f"No job found matching: {job_id}", err=True)
        sys.exit(1)
    elif len(matching_jobs) > 1:
        click.echo(f"Multiple jobs match '{job_id}':", err=True)
        for job in matching_jobs:
            click.echo(f"  {job['id']}", err=True)
        sys.exit(1)
    
    full_job_id = matching_jobs[0]['id']
    job = matching_jobs[0]
    
    # Check job status
    if job['status'] not in ['queued', 'failed']:
        click.echo(f"Job {full_job_id} is {job['status']} (must be queued or failed)", err=True)
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
    from ..worker.base import Worker
    worker = Worker(
        job_db=job_db,
        worker_id=worker_id,
        working_dir=working_dir,
        sync_enabled=not no_sync
    )
    
    # Simple sync function
    def print_sync(item):
        print(f"[SYNC] Would upload: {item.file_type} - {Path(item.file_path).name}")
    
    worker.sync_fn = print_sync
    
    # Claim and run the reserved job
    claimed_job = job_db.claim_reserved_job(full_job_id, worker_id)
    if not claimed_job:
        click.echo(f"Failed to claim reserved job {full_job_id}", err=True)
        sys.exit(1)
    
    # Execute directly
    worker.current_job_id = claimed_job['id']
    result = worker.execute_job(claimed_job)
    
    # Update job status
    if result['status'] == 'success':
        metrics = None
        if isinstance(result.get('result'), dict):
            metrics = result['result'].get('metrics')
        job_db.complete_job(claimed_job['id'], metrics)
        status_msg = click.style("COMPLETED", fg='green')
    else:
        job_db.fail_job(claimed_job['id'], result['error'])
        status_msg = click.style("FAILED", fg='red')
    
    click.echo("-" * 60)
    click.echo(f"Job {full_job_id}: {status_msg}")
    
    if result['status'] == 'failed':
        click.echo(f"\nError: {result['error']}")
        sys.exit(1)


@cli.command()
@click.pass_context
def validate(ctx):
    """Validate experiment setup and configuration."""
    job_db = ctx.obj['job_db']
    exp_path = Path(ctx.obj['base_path']) / ctx.obj['experiment']
    
    issues = []
    warnings = []
    
    # Check directory structure
    required_dirs = ['jobs', 'storage', 'sync_queue']
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
            running_jobs = [j for j in jobs if j['status'] == 'running']
            if running_jobs:
                from datetime import datetime
                now = datetime.utcnow()
                
                for job in running_jobs:
                    last_heartbeat = job.get('last_heartbeat')
                    if last_heartbeat:
                        last_time = datetime.fromisoformat(last_heartbeat)
                        stale_seconds = (now - last_time).total_seconds()
                        if stale_seconds > 300:
                            warnings.append(f"Job {job['id']} may be stale (no heartbeat for {int(stale_seconds)}s)")
    except Exception as e:
        issues.append(f"Error reading jobs: {e}")
    
    # Display results
    if issues:
        click.echo(click.style("✗ Validation FAILED", fg='red', bold=True))
        click.echo("\nIssues found:")
        for issue in issues:
            click.echo(f"  ✗ {issue}")
    else:
        click.echo(click.style("✓ Validation PASSED", fg='green', bold=True))
    
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


# Add this import at the top of the file
import time
```

### 2. Create tests/implementation/test_step_2_5.py
```python
"""Test job management commands."""
import tempfile
import time
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from click.testing import CliRunner

from src.dr_exp.cli.main import cli
from src.dr_exp.core.job_db import JobDB


def test_cli_kill():
    """Test killing jobs."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create jobs
        job_db = JobDB(base_path=tmpdir, experiment_name='test_exp')
        config = {'_target_': 'test.train'}
        
        job1 = job_db.create_job(config)
        job2 = job_db.create_job(config)
        job_db.claim_next_job('worker')  # job2 is running
        
        # Kill queued job
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'kill', job1[:8]  # Partial ID
        ])
        
        assert result.exit_code == 0
        assert f'Killed job: {job1}' in result.output
        
        # Verify job is killed
        job = job_db.get_job(job1)
        assert job['status'] == 'killed'
        
        # Kill running job
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'kill', job2
        ])
        
        assert result.exit_code == 0
        
        # Try to kill non-existent job
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'kill', 'fake_id'
        ])
        
        assert result.exit_code == 1
        assert 'No job found matching' in result.output
        


def test_cli_boost():
    """Test boosting job priority."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create jobs
        job_db = JobDB(base_path=tmpdir, experiment_name='test_exp')
        config = {'_target_': 'test.train'}
        
        job1 = job_db.create_job(config, priority=100)
        job2 = job_db.create_job(config, priority=200)
        
        # Boost job1
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'boost', job1[:8],  # Partial ID
            '--priority', '900'
        ])
        
        assert result.exit_code == 0
        assert f'Boosted job: {job1} (100 → 900)' in result.output
        
        # Verify priority changed
        job = job_db.get_job(job1)
        assert job['priority'] == 900
        
        # Boost multiple jobs
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'boost', job1, job2,
            '--priority', '950'
        ])
        
        assert result.exit_code == 0
        assert 'Boosted 2 job(s)' in result.output
        


def test_cli_recover():
    """Test recovering stale jobs."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create stale job
        job_db = JobDB(base_path=tmpdir, experiment_name='test_exp')
        config = {'_target_': 'test.train'}
        
        job_id = job_db.create_job(config)
        job_db.claim_next_job('worker')
        
        # Make it stale by backdating
        old_time = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        job_db.update_job(job_id, {'started_at': old_time})
        
        # Test dry run
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'recover',
            '--dry-run',
            '--threshold', '300'
        ])
        
        assert result.exit_code == 0
        assert 'Would recover 1 stale job(s)' in result.output
        assert job_id in result.output
        
        # Actually recover
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'recover',
            '--threshold', '300'
        ])
        
        assert result.exit_code == 0
        assert 'Recovered 1 stale job(s)' in result.output
        
        # Verify job is queued again
        job = job_db.get_job(job_id)
        assert job['status'] == 'queued'
        


def test_cli_sync_status():
    """Test sync status command."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create experiment with sync items
        job_db = JobDB(base_path=tmpdir, experiment_name='test_exp')
        
        # Add some sync items
        from src.dr_exp.sync.queue import SyncQueue, SyncItem
        sync_queue = SyncQueue(job_db.get_sync_queue_path())
        
        # Add pending item
        item1 = SyncItem(
            id='sync1',
            job_id='job1',
            file_path='/tmp/file1.txt',
            file_type='metrics',
            metadata={},
            created_at=datetime.utcnow().isoformat()
        )
        sync_queue.add_item(item1)
        
        # Add failed item
        item2 = SyncItem(
            id='sync2',
            job_id='job2',
            file_path='/tmp/file2.txt',
            file_type='model',
            metadata={},
            created_at=datetime.utcnow().isoformat()
        )
        sync_queue.add_item(item2)
        sync_queue.mark_attempt('sync2', 'Network error')
        
        # Get status
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'sync-status'
        ])
        
        assert result.exit_code == 0
        assert 'Sync Queue Status:' in result.output
        assert 'Pending:   2' in result.output
        
        # Get verbose status
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'sync-status',
            '--verbose'
        ])
        
        assert result.exit_code == 0
        assert 'Pending items:' in result.output
        assert 'sync1' in result.output
        assert 'sync2' in result.output
        assert 'Network error' in result.output
        


def test_cli_run_one():
    """Test running a single job."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a job
        job_db = JobDB(base_path=tmpdir, experiment_name='test_exp')
        config = {
            '_target_': 'src.dr_exp.trainers.test_trainer.train',
            'epochs': 2
        }
        job_id = job_db.create_job(config, priority=500)
        
        # Run the specific job
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'run-one', job_id[:8],  # Partial ID
            '--no-sync'
        ])
        
        assert result.exit_code == 0
        assert f'Running job: {job_id}' in result.output
        assert 'Job ' in result.output and 'COMPLETED' in result.output
        
        # Verify job completed
        job = job_db.get_job(job_id)
        assert job['status'] == 'completed'
        
        # Test running failed job
        config['fail_rate'] = 1.0
        fail_job_id = job_db.create_job(config)
        
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'run-one', fail_job_id
        ])
        
        assert result.exit_code == 1
        assert 'FAILED' in result.output
        assert 'Simulated training failure' in result.output
        


def test_cli_validate():
    """Test experiment validation."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test uninitialized experiment
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'missing_exp',
            'validate'
        ])
        
        assert result.exit_code == 1
        assert 'Validation FAILED' in result.output
        assert 'Missing directory' in result.output
        
        # Initialize experiment
        runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'good_exp',
            'init'
        ])
        
        # Validate good experiment
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'good_exp',
            'validate'
        ])
        
        assert result.exit_code == 0
        assert 'Validation PASSED' in result.output
        assert 'No jobs found' in result.output  # Warning
        
        # Add a stale job
        job_db = JobDB(base_path=tmpdir, experiment_name='good_exp')
        config = {'_target_': 'test.train'}
        job_id = job_db.create_job(config)
        job_db.claim_next_job('worker')
        
        # Backdate to make stale
        old_time = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        job_db.update_job(job_id, {'last_heartbeat': old_time})
        
        # Validate with stale job
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'good_exp',
            'validate'
        ])
        
        assert result.exit_code == 0
        assert 'may be stale' in result.output
        


def test_cli_partial_id_matching():
    """Test partial job ID matching."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create jobs with similar IDs
        job_db = JobDB(base_path=tmpdir, experiment_name='test_exp')
        config = {'_target_': 'test.train'}
        
        # Create multiple jobs
        jobs = []
        for _ in range(3):
            jobs.append(job_db.create_job(config))
        
        # Test unique partial match
        partial = jobs[0][:8]
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'kill', partial
        ])
        
        assert result.exit_code == 0
        assert f'Killed job: {jobs[0]}' in result.output
        
        # Test ambiguous partial match
        # Create a scenario where partial IDs might conflict
        # This is unlikely with UUIDs but we'll test the handling
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'kill', 'a'  # Very short partial that might match multiple
        ])
        
        # Should either succeed with one match or show multiple matches
        if 'Multiple jobs match' in result.output:
            assert result.exit_code == 1
        


```

## Validation
```bash
# Run the test with pytest
pt tests/implementation/test_step_2_5.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_2_5.py::test_cli_kill PASSED
# tests/implementation/test_step_2_5.py::test_cli_boost PASSED
# tests/implementation/test_step_2_5.py::test_cli_recover PASSED
# tests/implementation/test_step_2_5.py::test_cli_sync_status PASSED
# tests/implementation/test_step_2_5.py::test_cli_run_one PASSED
# tests/implementation/test_step_2_5.py::test_cli_validate PASSED
# tests/implementation/test_step_2_5.py::test_cli_partial_id_matching PASSED
# ============================== 7 passed in X.XXs ===============================

# Test actual CLI commands
# Initialize experiment
dr_exp --base-path /tmp/test --experiment job_mgmt init

# Create some test jobs
dr_exp --base-path /tmp/test --experiment job_mgmt submit configs/test_job.yaml
dr_exp --base-path /tmp/test --experiment job_mgmt submit configs/test_job.yaml --priority 900

# List jobs
dr_exp --base-path /tmp/test --experiment job_mgmt list

# Kill a job (use partial ID from list)
dr_exp --base-path /tmp/test --experiment job_mgmt kill <partial_id>

# Boost priority
dr_exp --base-path /tmp/test --experiment job_mgmt boost <partial_id> --priority 950

# Validate experiment
dr_exp --base-path /tmp/test --experiment job_mgmt validate

# Run code quality checks
ckdr
```

## Common Mistakes
- DO NOT: Require full UUIDs - support partial matching for user convenience
- DO NOT: Exit silently on errors - always provide clear error messages
- DO NOT: Modify job state without user confirmation (except recover with dry-run)
- DO NOT: Add complex filtering - keep commands simple and focused
- DO NOT: Forget to handle multiple job IDs where it makes sense

## Next Step
Proceed to Step 2.6: Training Integration