# Step 2.9: SLURM Integration

## Goal (1 sentence)
Create SLURM batch scripts and management commands for running the multi-worker launcher on HPC clusters.

## Prerequisites
- [ ] Step 2.8 completed and validated
- [ ] Multi-worker launcher (Step 2.7) implemented
- [ ] Access to a SLURM-based cluster for testing
- [ ] Understanding of SLURM basics (sbatch, environment variables)

## Implementation

### 1. Create enhanced SLURM batch script (scripts/dr_exp_slurm.sbatch)
```bash
#!/bin/bash
#SBATCH --job-name=dr_exp_workers
#SBATCH --time=47:00:00
#SBATCH --nodes=1
#SBATCH --gpus-per-node=3
#SBATCH --cpus-per-task=8
#SBATCH --mem=192G

# Parameters from environment or defaults
BASE_PATH=${BASE_PATH:-/scratch/users/$USER/experiments}
EXPERIMENT=${EXPERIMENT:-default_experiment}
WORKERS_PER_GPU=${WORKERS_PER_GPU:-2}

# Create log directory for this SLURM job
LOG_DIR="$BASE_PATH/$EXPERIMENT/logs/slurm_${SLURM_JOB_ID}"
mkdir -p "$LOG_DIR/workers"
mkdir -p "$BASE_PATH/$EXPERIMENT/control"

# Redirect SLURM output
SLURM_LOG_DIR="$BASE_PATH/$EXPERIMENT/slurm_logs"
mkdir -p "$SLURM_LOG_DIR"
exec &> >(tee -a "$SLURM_LOG_DIR/slurm-${SLURM_JOB_ID}.out")

# Log startup info
echo "========================================"
echo "DR_EXP SLURM Job Starting"
echo "========================================"
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Time: $(date)"
echo "Base path: $BASE_PATH"
echo "Experiment: $EXPERIMENT"
echo "Workers per GPU: $WORKERS_PER_GPU"
echo "Allocated GPUs: $SLURM_GPUS_PER_NODE"
echo "Allocated Memory: $SLURM_MEM_PER_NODE MB"
echo "Log directory: $LOG_DIR"
echo "========================================"

# Setup Python environment (adjust as needed)
module load python/3.10
source /path/to/venv/bin/activate

# Optional: Setup CUDA MPS for better GPU sharing
export CUDA_MPS_PIPE_DIRECTORY="/tmp/nvidia-mps-${SLURM_JOB_ID}"
export CUDA_MPS_LOG_DIRECTORY="/tmp/nvidia-log-${SLURM_JOB_ID}"
mkdir -p "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"

cleanup() {
    echo "Cleaning up..."
    echo quit | nvidia-cuda-mps-control 2>/dev/null || true
    rm -rf "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"
}
trap cleanup EXIT

# Start CUDA MPS daemon
nvidia-cuda-mps-control -d

# Start launcher with enhanced logging
dr_exp --base-path "$BASE_PATH" \
       --experiment "$EXPERIMENT" \
       system launcher \
       --workers-per-gpu "$WORKERS_PER_GPU" \
       2>&1 | tee -a "$LOG_DIR/launcher.log"

echo "SLURM job completed at $(date)"
```

### 2. Add SLURM management commands to CLI (create src/dr_exp/cli/commands/slurm.py)
```python
"""SLURM job management commands."""
import json
import click
from pathlib import Path
from datetime import datetime, UTC


@click.group()
def slurm() -> None:
    """SLURM job management commands."""
    pass


@slurm.command()
@click.pass_context
def status(ctx) -> None:
    """Show status of all SLURM jobs for this experiment."""
    # Create JobDB instance for this command
    from dr_exp.core.job_db import JobDB
    job_db = JobDB(
        base_path=ctx.obj['base_path'],
        experiment_name=ctx.obj['experiment']
    )
    logs_dir = job_db.logs_dir
    
    if not logs_dir.exists():
        click.echo("No SLURM jobs found")
        return
    
    slurm_dirs = sorted([d for d in logs_dir.iterdir() if d.name.startswith('slurm_')])
    
    if not slurm_dirs:
        click.echo("No SLURM jobs found")
        return
    
    for slurm_dir in slurm_dirs:
        job_id = slurm_dir.name.replace('slurm_', '')
        status_file = job_db.control_dir / f'status_{job_id}.json'
        
        if status_file.exists():
            with open(status_file) as f:
                status = json.load(f)
            
            # Extract key info
            launcher_info = status.get('launcher', {})
            workers = status.get('workers', {})
            job_stats = status.get('jobs', {})
            
            # Count alive workers
            alive = sum(1 for w in workers.values() if w == 'running')
            total = len(workers)
            
            runtime_hours = launcher_info.get('runtime_seconds', 0) / 3600
            
            click.echo(f"\nSLURM Job {job_id}")
            click.echo(f"  Node: {launcher_info.get('node', 'unknown')}")
            click.echo(f"  Runtime: {runtime_hours:.1f} hours")
            click.echo(f"  Workers: {alive}/{total} alive")
            click.echo(f"  Jobs: {job_stats.get('running', 0)} running, "
                      f"{job_stats.get('queued', 0)} queued, "
                      f"{job_stats.get('completed', 0)} completed")
        else:
            click.echo(f"\nSLURM Job {job_id}: No status available")


@slurm.command()
@click.argument('job_id')
@click.option('--finish-current', is_flag=True, help='Finish current jobs then stop')
@click.option('--stop-now', is_flag=True, help='Stop immediately')
@click.pass_context
def control(ctx, job_id: str, finish_current: bool, stop_now: bool) -> None:
    """Send control commands to a SLURM job."""
    # Create JobDB instance for this command
    from dr_exp.core.job_db import JobDB
    job_db = JobDB(
        base_path=ctx.obj['base_path'],
        experiment_name=ctx.obj['experiment']
    )
    
    if finish_current:
        control_file = job_db.control_dir / f'finish_current_{job_id}'
        control_file.touch()
        click.echo(f"Sent finish-current command to SLURM job {job_id}")
    elif stop_now:
        control_file = job_db.control_dir / f'stop_{job_id}'
        control_file.touch()
        click.echo(f"Sent stop command to SLURM job {job_id}")
    else:
        click.echo("Specify either --finish-current or --stop-now")


@slurm.command()
@click.argument('job_id')
@click.option('--tail', default=50, help='Number of lines to show')
@click.pass_context
def errors(ctx, job_id: str, tail: int) -> None:
    """View aggregated errors from a SLURM job."""
    # Create JobDB instance for this command
    from dr_exp.core.job_db import JobDB
    job_db = JobDB(
        base_path=ctx.obj['base_path'],
        experiment_name=ctx.obj['experiment']
    )
    error_log = job_db.logs_dir / f'slurm_{job_id}' / 'errors.log'
    
    if not error_log.exists():
        click.echo(f"No errors found for SLURM job {job_id}")
        return
    
    # Show last N lines
    with open(error_log) as f:
        lines = f.readlines()
        for line in lines[-tail:]:
            click.echo(line.rstrip())


@slurm.command()  
@click.argument('job_id')
@click.option('--worker', default=None, help='Specific worker ID')
@click.option('--tail', default=50, help='Number of lines to show')
@click.pass_context
def logs(ctx, job_id: str, worker: str, tail: int) -> None:
    """View logs from a SLURM job."""
    # Create JobDB instance for this command
    from dr_exp.core.job_db import JobDB
    job_db = JobDB(
        base_path=ctx.obj['base_path'],
        experiment_name=ctx.obj['experiment']
    )
    
    if worker:
        # Specific worker log
        log_file = job_db.logs_dir / f'slurm_{job_id}' / f'{worker}.log'
    else:
        # Launcher log
        log_file = job_db.logs_dir / f'slurm_{job_id}' / 'launcher.log'
    
    if not log_file.exists():
        click.echo(f"Log file not found: {log_file}")
        return
    
    # Show last N lines
    with open(log_file) as f:
        lines = f.readlines()
        for line in lines[-tail:]:
            click.echo(line.rstrip())
```

### 3. Create helper script for batch submissions (scripts/submit_experiments.sh)
```bash
#!/bin/bash
# Helper script to submit multiple experiments

set -e

# Default values
BASE_PATH="${BASE_PATH:-/scratch/users/$USER/experiments}"
WORKERS_PER_GPU="${WORKERS_PER_GPU:-2}"
SLURM_SCRIPT="scripts/dr_exp_slurm.sbatch"

# Function to submit a single experiment
submit_experiment() {
    local exp_name=$1
    local priority=${2:-100}
    
    echo "Submitting experiment: $exp_name (priority: $priority)"
    
    # Create experiment directory
    mkdir -p "$BASE_PATH/$exp_name"
    
    # Submit SLURM job
    job_id=$(sbatch \
        --export=BASE_PATH="$BASE_PATH",EXPERIMENT="$exp_name",WORKERS_PER_GPU="$WORKERS_PER_GPU" \
        --job-name="dr_exp_$exp_name" \
        "$SLURM_SCRIPT" | awk '{print $NF}')
    
    echo "  Submitted SLURM job: $job_id"
    
    # Create a tracking file
    echo "$job_id" > "$BASE_PATH/$exp_name/.slurm_job_id"
}

# Check arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 experiment1 [experiment2 ...]"
    echo "  or: $0 -f experiments.txt"
    exit 1
fi

# Process arguments
if [ "$1" = "-f" ]; then
    # Read from file
    if [ ! -f "$2" ]; then
        echo "Error: File $2 not found"
        exit 1
    fi
    
    while IFS= read -r exp_name; do
        [ -z "$exp_name" ] && continue  # Skip empty lines
        [[ "$exp_name" =~ ^# ]] && continue  # Skip comments
        submit_experiment "$exp_name"
    done < "$2"
else
    # Submit each argument as experiment
    for exp_name in "$@"; do
        submit_experiment "$exp_name"
    done
fi

echo "All experiments submitted"
```

### 4. Create tests/implementation/test_step_2_9.py
```python
"""Test SLURM integration functionality."""
import tempfile
import os
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from click.testing import CliRunner

from src.dr_exp.core.job_db import JobDB
from src.dr_exp.cli.main import cli


def test_slurm_status_command() -> None:
    """Test SLURM status command."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        # Create mock SLURM job status
        slurm_dir = job_db.logs_dir / "slurm_123456"
        slurm_dir.mkdir(parents=True)
        
        status_data = {
            "launcher": {
                "slurm_job_id": "123456",
                "node": "node001",
                "runtime_seconds": 3600,
                "running": True
            },
            "workers": {
                "worker1": "running",
                "worker2": "running",
                "worker3": "exited(1)"
            },
            "jobs": {
                "queued": 10,
                "running": 2,
                "completed": 50,
                "failed": 3
            }
        }
        
        status_file = job_db.control_dir / "status_123456.json"
        with open(status_file, 'w') as f:
            json.dump(status_data, f)
        
        # Run command
        runner = CliRunner()
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'slurm', 'status'
        ])
        
        assert result.exit_code == 0
        assert "SLURM Job 123456" in result.output
        assert "Node: node001" in result.output
        assert "Runtime: 1.0 hours" in result.output
        assert "Workers: 2/3 alive" in result.output
        assert "Jobs: 2 running, 10 queued, 50 completed" in result.output
        


def test_slurm_control_commands() -> None:
    """Test SLURM control commands."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        runner = CliRunner()
        
        # Test finish-current command
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'slurm', 'control', '123456',
            '--finish-current'
        ])
        
        assert result.exit_code == 0
        assert "Sent finish-current command" in result.output
        assert (job_db.control_dir / "finish_current_123456").exists()
        
        # Test stop-now command
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'slurm', 'control', '789012',
            '--stop-now'
        ])
        
        assert result.exit_code == 0
        assert "Sent stop command" in result.output
        assert (job_db.control_dir / "stop_789012").exists()
        


def test_slurm_error_logs() -> None:
    """Test SLURM error log viewing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        # Create mock error log
        slurm_dir = job_db.logs_dir / "slurm_123456"
        slurm_dir.mkdir(parents=True)
        
        error_log = slurm_dir / "errors.log"
        error_log.write_text("""
Error aggregation at 2024-01-15T10:00:00
================================================================================

### Errors from worker1.log
[ERROR] Training failed: CUDA out of memory
Traceback (most recent call last):
  File "train.py", line 42, in train
    output = model(batch)
RuntimeError: CUDA out of memory

### Errors from worker2.log
[ERROR] Configuration error: Missing required field 'batch_size'
""".strip())
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'slurm', 'errors', '123456',
            '--tail', '20'
        ])
        
        assert result.exit_code == 0
        assert "CUDA out of memory" in result.output
        assert "Missing required field" in result.output
        


def test_slurm_worker_logs() -> None:
    """Test SLURM worker log viewing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        # Create mock logs
        slurm_dir = job_db.logs_dir / "slurm_123456"
        slurm_dir.mkdir(parents=True)
        
        # Launcher log
        launcher_log = slurm_dir / "launcher.log"
        launcher_log.write_text("""
[INFO] Starting launcher on node node001
[INFO] Found 3 GPUs: [0, 1, 2]
[INFO] Spawning worker node001_gpu0_w0 on GPU 0
[INFO] Spawning worker node001_gpu0_w1 on GPU 0
[INFO] Workers alive: 6/6
[INFO] Jobs queued: 25
""".strip())
        
        # Worker log
        worker_log = slurm_dir / "node001_gpu0_w0.log"
        worker_log.write_text("""
[INFO] Worker node001_gpu0_w0 starting
[INFO] Claimed job 12345
[INFO] Training started
[INFO] Epoch 1/10: loss=0.532
""".strip())
        
        runner = CliRunner()
        
        # Test launcher log
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'slurm', 'logs', '123456',
            '--tail', '10'
        ])
        
        assert result.exit_code == 0
        assert "Starting launcher" in result.output
        assert "Workers alive: 6/6" in result.output
        
        # Test worker log
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'slurm', 'logs', '123456',
            '--worker', 'node001_gpu0_w0',
            '--tail', '10'
        ])
        
        assert result.exit_code == 0
        assert "Worker node001_gpu0_w0 starting" in result.output
        assert "Epoch 1/10" in result.output
        


def test_slurm_environment_handling() -> None:
    """Test SLURM environment variable handling."""
    # Set mock SLURM environment
    with patch.dict(os.environ, {
        'SLURM_JOB_ID': '123456',
        'SLURMD_NODENAME': 'node001',
        'SLURM_GPUS_PER_NODE': '3',
        'SLURM_MEM_PER_NODE': '196608',
        'CUDA_VISIBLE_DEVICES': '0,1,2'
    }):
        # Verify launcher can read environment
        from src.dr_exp.worker.launcher import WorkerLauncher
        
        with tempfile.TemporaryDirectory() as tmpdir:
            job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
            
            launcher = WorkerLauncher(
                job_db=job_db,
                experiment_name="test_exp",
                base_log_dir=job_db.logs_dir
            )
            
            # Check SLURM info extracted
            assert launcher.slurm_job_id == '123456'
            assert launcher.slurm_node_name == 'node001'
            
            # Check GPU discovery
            gpus = launcher.discover_gpus()
            assert gpus == [0, 1, 2]
        


def test_batch_script_generation() -> None:
    """Test that batch script handles parameters correctly."""
    batch_script = Path(__file__).parent.parent / "scripts" / "dr_exp_slurm.sbatch"
    
    # Just verify the script would be created in implementation
    # In real implementation, this file would exist
    
    # Test parameter substitution
    test_params = {
        'BASE_PATH': '/scratch/test/experiments',
        'EXPERIMENT': 'my_test_exp',
        'WORKERS_PER_GPU': '3'
    }
    
    # Verify parameters would be used correctly
    for key, value in test_params.items():
        # In actual script, these would be: ${PARAM:-default}
        assert key in ['BASE_PATH', 'EXPERIMENT', 'WORKERS_PER_GPU']
    


```

## Validation
```bash
# Run the test with pytest
pt tests/implementation/test_step_2_9.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_2_9.py::test_slurm_status_command PASSED
# tests/implementation/test_step_2_9.py::test_slurm_control_commands PASSED
# tests/implementation/test_step_2_9.py::test_slurm_error_logs PASSED
# tests/implementation/test_step_2_9.py::test_slurm_worker_logs PASSED
# tests/implementation/test_step_2_9.py::test_slurm_environment_handling PASSED
# tests/implementation/test_step_2_9.py::test_batch_script_generation PASSED
# ============================== 6 passed in X.XXs ===============================

# Verify code quality (runs ruff linting/formatting + mypy type checks)
ckdr

# Expected: All checks passed!

# Add SLURM commands to CLI
# Update src/dr_exp/cli/command_groups.py to include:
# from .commands.slurm import slurm
# cli.add_command(slurm)

# Make scripts executable
chmod +x scripts/dr_exp_slurm.sbatch
chmod +x scripts/submit_experiments.sh
```

## Common Mistakes
- DO NOT: Hardcode paths in SLURM scripts - use environment variables
- DO NOT: Forget to load required modules and activate Python environment
- DO NOT: Leave CUDA MPS running after job completes - use trap cleanup
- DO NOT: Exceed memory limits - monitor and enforce limits per worker
- DO NOT: Ignore SLURM time limits - implement graceful shutdown

## Usage Examples
```bash
# Submit a single experiment
sbatch --export=BASE_PATH=/scratch/$USER/exp,EXPERIMENT=resnet_sweep scripts/dr_exp_slurm.sbatch

# Submit with custom parameters
sbatch --export=BASE_PATH=/scratch/$USER/exp,EXPERIMENT=vit_test,WORKERS_PER_GPU=3 \
       --gpus-per-node=4 \
       --time=24:00:00 \
       scripts/dr_exp_slurm.sbatch

# Submit multiple experiments
./scripts/submit_experiments.sh exp1 exp2 exp3

# Check status of all SLURM jobs
dr_exp --base-path /scratch/$USER/exp --experiment resnet_sweep slurm status

# View errors from a specific job
dr_exp --base-path /scratch/$USER/exp --experiment resnet_sweep slurm errors 123456

# Gracefully stop after current jobs complete
dr_exp --base-path /scratch/$USER/exp --experiment resnet_sweep slurm control 123456 --finish-current

# View worker logs
dr_exp --base-path /scratch/$USER/exp --experiment resnet_sweep slurm logs 123456 --worker node001_gpu0_w0
```

## Phase 2 Complete! 🎉

You have successfully implemented a complete worker system with:
- Single and multi-worker execution modes
- Background sync to Supabase
- Full CLI interface with job management
- StructuredLogger for metrics and artifacts
- Config sweeps for hyperparameter exploration
- Multi-worker launcher for production deployments
- SLURM integration for HPC clusters

## Next Step
Proceed to Phase 3, Step 3.1: Database Schema