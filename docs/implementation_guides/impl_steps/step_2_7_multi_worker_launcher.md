# Step 2.7: Multi-Worker Launcher

## Goal (1 sentence)
Create a launcher that spawns and monitors multiple workers across available GPUs for long-running SLURM jobs.

## Prerequisites
- [ ] Step 2.6 completed and validated
- [ ] Worker class exists and can execute jobs
- [ ] CLI framework in place
- [ ] GPU environment with CUDA support

## Implementation

### 1. Create src/dr_exp/worker/launcher.py
```python
"""Multi-worker launcher for GPU clusters."""
import os
import signal
import subprocess
import sys
import time
import json
from pathlib import Path
from datetime import datetime, UTC
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class WorkerLauncher:
    """Launches and monitors multiple workers across GPUs."""
    
    def __init__(
        self,
        job_db,
        experiment_name: str,
        base_log_dir: Path,
        workers_per_gpu: int = 2,
        restart_on_failure: bool = True,
        max_runtime_hours: float = 47  # Leave buffer before 48h SLURM limit
    ):
        """Initialize launcher.
        
        Args:
            job_db: JobDB instance
            experiment_name: Name of experiment
            base_log_dir: Base directory for logs
            workers_per_gpu: Number of workers per GPU
            restart_on_failure: Whether to restart failed workers
            max_runtime_hours: Maximum runtime before graceful shutdown
        """
        self.job_db = job_db
        self.experiment_name = experiment_name
        self.workers_per_gpu = workers_per_gpu
        self.restart_on_failure = restart_on_failure
        self.max_runtime_seconds = max_runtime_hours * 3600
        
        # SLURM info
        self.slurm_job_id = os.environ.get('SLURM_JOB_ID', 'local')
        self.slurm_node_name = os.environ.get('SLURMD_NODENAME', 'local')
        
        # Create log directory
        self.log_dir = base_log_dir / f"slurm_{self.slurm_job_id}"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Control files
        self.control_dir = self.job_db.control_dir
        self.stop_file = self.control_dir / f"stop_{self.slurm_job_id}"
        self.finish_current_file = self.control_dir / f"finish_current_{self.slurm_job_id}"
        
        # Process tracking
        self.processes: Dict[str, subprocess.Popen] = {}
        self.worker_restarts: Dict[str, int] = {}
        self.start_time = time.time()
        self.running = False
        
        # Signal handling
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
    
    def discover_gpus(self) -> List[int]:
        """Discover available GPUs.
        
        Returns:
            List of GPU indices
        """
        # First check CUDA_VISIBLE_DEVICES
        cuda_visible = os.environ.get('CUDA_VISIBLE_DEVICES', '')
        if cuda_visible:
            try:
                return [int(gpu) for gpu in cuda_visible.split(',') if gpu.strip()]
            except ValueError:
                logger.warning(f"Invalid CUDA_VISIBLE_DEVICES: {cuda_visible}")
        
        # Fall back to nvidia-smi
        try:
            result = subprocess.run(
                ['nvidia-smi', '--list-gpus'],
                capture_output=True,
                text=True,
                check=True
            )
            gpu_count = len(result.stdout.strip().split('\n'))
            return list(range(gpu_count))
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("No GPUs detected, running in CPU mode")
            return []
    
    def spawn_worker(self, gpu_index: Optional[int], worker_index: int) -> str:
        """Spawn a single worker process.
        
        Args:
            gpu_index: GPU to assign (None for CPU)
            worker_index: Worker index on this GPU
            
        Returns:
            Worker ID
        """
        # Create unique worker ID
        if gpu_index is not None:
            worker_id = f"slurm{self.slurm_job_id}_{self.slurm_node_name}_gpu{gpu_index}_{worker_index}"
        else:
            worker_id = f"slurm{self.slurm_job_id}_{self.slurm_node_name}_cpu_{worker_index}"
        
        # Set up environment
        env = os.environ.copy()
        if gpu_index is not None:
            env['CUDA_VISIBLE_DEVICES'] = str(gpu_index)
        
        # Worker log file
        worker_log = self.log_dir / f"{worker_id}.log"
        
        # Launch worker process
        cmd = [
            sys.executable,
            '-m', 'dr_exp.cli',
            '--base-path', str(self.job_db.base_path),
            '--experiment', self.experiment_name,
            'worker', 'run',
            '--worker-id', worker_id,
            '--work-dir', str(self.log_dir / worker_id)
        ]
        
        logger.info(f"Spawning worker {worker_id} on GPU {gpu_index}")
        
        with open(worker_log, 'w') as log_file:
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid  # Create new process group
            )
        
        self.processes[worker_id] = process
        self.worker_restarts[worker_id] = self.worker_restarts.get(worker_id, 0) + 1
        
        return worker_id
    
    def check_worker_health(self) -> Dict[str, str]:
        """Check health of all workers.
        
        Returns:
            Dict of worker_id -> status
        """
        status = {}
        
        for worker_id, process in list(self.processes.items()):
            poll = process.poll()
            if poll is None:
                status[worker_id] = "running"
            else:
                status[worker_id] = f"exited({poll})"
                # Remove from tracking
                del self.processes[worker_id]
                
                # Check if we should restart
                if self.restart_on_failure and self.running:
                    if self.has_pending_jobs():
                        # Extract GPU info from worker ID
                        if '_gpu' in worker_id:
                            parts = worker_id.split('_gpu')
                            gpu_part = parts[1].split('_')[0]
                            gpu_index = int(gpu_part)
                            worker_index = int(parts[1].split('_')[1])
                            self.spawn_worker(gpu_index, worker_index)
                        elif '_cpu' in worker_id:
                            worker_index = int(worker_id.split('_cpu_')[1])
                            self.spawn_worker(None, worker_index)
        
        return status
    
    def has_pending_jobs(self) -> bool:
        """Check if there are queued jobs."""
        queued = self.job_db.list_jobs(status="queued")
        return len(queued) > 0
    
    def check_control_files(self) -> Optional[str]:
        """Check for control file commands.
        
        Returns:
            Command if found, None otherwise
        """
        if self.stop_file.exists():
            logger.info("Stop file detected")
            self.stop_file.unlink()
            return "stop"
        
        if self.finish_current_file.exists():
            logger.info("Finish-current file detected")
            self.finish_current_file.unlink()
            return "finish_current"
        
        return None
    
    def write_status(self):
        """Write launcher status to file."""
        worker_status = self.check_worker_health()
        
        status_data = {
            "launcher": {
                "slurm_job_id": self.slurm_job_id,
                "node": self.slurm_node_name,
                "start_time": datetime.fromtimestamp(self.start_time, UTC).isoformat(),
                "runtime_seconds": int(time.time() - self.start_time),
                "running": self.running
            },
            "workers": worker_status,
            "restarts": self.worker_restarts,
            "jobs": {
                "queued": len(self.job_db.list_jobs(status="queued")),
                "running": len(self.job_db.list_jobs(status="running")),
                "completed": len(self.job_db.list_jobs(status="completed")),
                "failed": len(self.job_db.list_jobs(status="failed"))
            }
        }
        
        status_file = self.control_dir / f"status_{self.slurm_job_id}.json"
        with open(status_file, 'w') as f:
            json.dump(status_data, f, indent=2)
    
    def aggregate_errors(self):
        """Aggregate errors from worker logs."""
        error_file = self.log_dir / "errors.log"
        
        with open(error_file, 'w') as err_out:
            err_out.write(f"Error aggregation at {datetime.now(UTC).isoformat()}\n")
            err_out.write("=" * 80 + "\n\n")
            
            for log_file in self.log_dir.glob("*.log"):
                if log_file.name == "errors.log":
                    continue
                
                # Look for errors in log
                errors_found = False
                with open(log_file) as f:
                    for line in f:
                        if any(marker in line.lower() for marker in ['error', 'exception', 'traceback']):
                            if not errors_found:
                                err_out.write(f"\n### Errors from {log_file.name}\n")
                                errors_found = True
                            err_out.write(line)
    
    def run(self):
        """Run the launcher main loop."""
        self.running = True
        logger.info(f"Starting launcher on node {self.slurm_node_name}")
        
        # Discover GPUs
        gpus = self.discover_gpus()
        logger.info(f"Found {len(gpus)} GPUs: {gpus}")
        
        # Spawn initial workers
        if gpus:
            for gpu_index in gpus:
                for worker_index in range(self.workers_per_gpu):
                    self.spawn_worker(gpu_index, worker_index)
        else:
            # CPU only mode
            for worker_index in range(self.workers_per_gpu):
                self.spawn_worker(None, worker_index)
        
        # Main monitoring loop
        last_status_write = 0
        last_maintenance = 0
        
        while self.running:
            try:
                # Check runtime limit
                if time.time() - self.start_time > self.max_runtime_seconds:
                    logger.info("Reached maximum runtime, initiating graceful shutdown")
                    self.stop()
                    break
                
                # Check control files
                command = self.check_control_files()
                if command == "stop":
                    self.stop()
                    break
                elif command == "finish_current":
                    self.finish_current()
                    break
                
                # Write status every minute
                if time.time() - last_status_write > 60:
                    self.write_status()
                    last_status_write = time.time()
                
                # Run maintenance every 10 minutes
                if time.time() - last_maintenance > 600:
                    self.maintenance()
                    last_maintenance = time.time()
                
                # Check worker health
                self.check_worker_health()
                
                # Sleep briefly
                time.sleep(5)
                
            except KeyboardInterrupt:
                logger.info("Received interrupt, shutting down")
                self.stop()
                break
        
        # Final cleanup
        self.cleanup()
    
    def maintenance(self):
        """Run periodic maintenance tasks."""
        logger.info("Running maintenance")
        
        # Recover stale jobs
        recovered = self.job_db.recover_stale_jobs()
        if recovered:
            logger.info(f"Recovered {len(recovered)} stale jobs")
        
        # Aggregate errors
        self.aggregate_errors()
        
        # Log summary
        logger.info(f"Workers alive: {len(self.processes)}")
        logger.info(f"Jobs queued: {len(self.job_db.list_jobs(status='queued'))}")
        logger.info(f"Runtime: {(time.time() - self.start_time) / 3600:.1f} hours")
    
    def stop(self):
        """Stop all workers immediately."""
        self.running = False
        logger.info("Stopping all workers")
        
        # Send SIGTERM to all workers
        for worker_id, process in self.processes.items():
            logger.info(f"Terminating {worker_id}")
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        
        # Wait briefly for graceful shutdown
        time.sleep(5)
        
        # Force kill any remaining
        for worker_id, process in list(self.processes.items()):
            if process.poll() is None:
                logger.warning(f"Force killing {worker_id}")
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
    
    def finish_current(self):
        """Let workers finish current jobs then stop."""
        self.running = False
        logger.info("Finishing current jobs then stopping")
        
        # Don't spawn new workers
        self.restart_on_failure = False
        
        # Wait for all workers to finish
        while self.processes:
            self.check_worker_health()
            
            # Check if any are still working
            running_jobs = self.job_db.list_jobs(status="running")
            if not running_jobs:
                logger.info("No jobs running, stopping workers")
                self.stop()
                break
            
            time.sleep(5)
    
    def cleanup(self):
        """Final cleanup tasks."""
        logger.info("Running final cleanup")
        
        # Write final status
        self.write_status()
        
        # Aggregate all errors
        self.aggregate_errors()
        
        # Clean up control files
        for f in [self.stop_file, self.finish_current_file]:
            if f.exists():
                f.unlink()
        
        # Remove status file on clean exit
        status_file = self.control_dir / f"status_{self.slurm_job_id}.json"
        if status_file.exists():
            status_file.unlink()
        
        logger.info("Launcher shutdown complete")
    
    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}")
        self.stop()
```

### 2. Add launcher command to CLI (update src/dr_exp/cli/commands/launcher.py)
```python
"""Launcher command for spawning multiple workers."""
import click
from pathlib import Path
from dr_exp.worker.launcher import WorkerLauncher


@click.command()
@click.option('--workers-per-gpu', default=2, help='Workers per GPU')
@click.option('--max-hours', default=47, help='Maximum runtime in hours')
@click.pass_context
def launcher(ctx, workers_per_gpu: int, max_hours: float):
    """Run multi-worker launcher for SLURM jobs."""
    job_db = ctx.obj['job_db']
    experiment_name = ctx.obj['experiment_name']
    
    # Use logs directory under experiment
    log_dir = job_db.logs_dir
    
    launcher = WorkerLauncher(
        job_db=job_db,
        experiment_name=experiment_name,
        base_log_dir=log_dir,
        workers_per_gpu=workers_per_gpu,
        max_runtime_hours=max_hours
    )
    
    launcher.run()
```

### 3. Create control script (scripts/launcher_control.py)
```python
#!/usr/bin/env python3
"""Send control commands to running launchers."""
import click
from pathlib import Path


@click.command()
@click.argument('command', type=click.Choice(['stop', 'finish-current', 'status']))
@click.option('--base-path', required=True, help='Base experiment path')
@click.option('--experiment', required=True, help='Experiment name')
@click.option('--job-id', help='SLURM job ID (defaults to all)')
def main(command: str, base_path: str, experiment: str, job_id: str = None):
    """Send control commands to launcher."""
    control_dir = Path(base_path) / experiment / "control"
    
    if command == "status":
        # Show status files
        for status_file in control_dir.glob("status_*.json"):
            print(f"\nStatus from {status_file.name}:")
            print(status_file.read_text())
    else:
        # Create control file
        if job_id:
            targets = [job_id]
        else:
            # Find all active launchers
            targets = []
            for status_file in control_dir.glob("status_*.json"):
                job_id = status_file.stem.replace("status_", "")
                targets.append(job_id)
        
        if not targets:
            print("No active launchers found")
            return
        
        for target in targets:
            if command == "stop":
                control_file = control_dir / f"stop_{target}"
            elif command == "finish-current":
                control_file = control_dir / f"finish_current_{target}"
            
            control_file.touch()
            print(f"Sent {command} to launcher {target}")


if __name__ == "__main__":
    main()
```

### 4. Create tests/implementation/test_step_2_7.py
```python
"""Test multi-worker launcher functionality."""
import tempfile
import time
import os
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.dr_exp.core.job_db import JobDB
from src.dr_exp.worker.launcher import WorkerLauncher


def test_launcher_init():
    """Test launcher initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs",
            workers_per_gpu=2
        )
        
        assert launcher.workers_per_gpu == 2
        assert launcher.log_dir.exists()
        assert launcher.slurm_job_id == "local"  # Not in SLURM
        


def test_gpu_discovery():
    """Test GPU discovery methods."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs"
        )
        
        # Test CUDA_VISIBLE_DEVICES parsing
        with patch.dict(os.environ, {'CUDA_VISIBLE_DEVICES': '0,1,3'}):
            gpus = launcher.discover_gpus()
            assert gpus == [0, 1, 3]
        
        # Test empty CUDA_VISIBLE_DEVICES
        with patch.dict(os.environ, {'CUDA_VISIBLE_DEVICES': ''}):
            with patch('subprocess.run') as mock_run:
                # Simulate no GPUs
                mock_run.side_effect = FileNotFoundError()
                gpus = launcher.discover_gpus()
                assert gpus == []
        


def test_worker_spawning():
    """Test spawning worker processes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs"
        )
        
        # Mock subprocess to avoid actually spawning
        with patch('subprocess.Popen') as mock_popen:
            mock_process = Mock()
            mock_process.poll.return_value = None  # Still running
            mock_popen.return_value = mock_process
            
            # Spawn GPU worker
            worker_id = launcher.spawn_worker(0, 0)
            assert "gpu0_0" in worker_id
            assert worker_id in launcher.processes
            
            # Spawn CPU worker
            worker_id = launcher.spawn_worker(None, 0)
            assert "cpu_0" in worker_id
            
            # Verify environment was set correctly
            calls = mock_popen.call_args_list
            gpu_call_env = calls[0][1]['env']
            assert gpu_call_env['CUDA_VISIBLE_DEVICES'] == '0'
        


def test_health_monitoring():
    """Test worker health monitoring and restart."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        # Create a queued job
        job_db.create_job({"_target_": "dr_exp.training.dummy_trainer.train_dummy"})
        
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs"
        )
        launcher.running = True
        
        # Mock process that exits
        mock_process = Mock()
        mock_process.poll.return_value = 1  # Exit code 1
        
        launcher.processes["test_worker_gpu0_0"] = mock_process
        
        with patch.object(launcher, 'spawn_worker') as mock_spawn:
            status = launcher.check_worker_health()
            
            # Should report as exited
            assert status["test_worker_gpu0_0"] == "exited(1)"
            
            # Should restart because we have pending jobs
            mock_spawn.assert_called_once_with(0, 0)
        


def test_control_files():
    """Test control file handling."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs"
        )
        
        # Test stop file
        launcher.stop_file.touch()
        command = launcher.check_control_files()
        assert command == "stop"
        assert not launcher.stop_file.exists()  # Should be deleted
        
        # Test finish-current file
        launcher.finish_current_file.touch()
        command = launcher.check_control_files()
        assert command == "finish_current"
        assert not launcher.finish_current_file.exists()
        


def test_status_writing():
    """Test status file generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        # Create some jobs
        job_db.create_job({"_target_": "dr_exp.training.dummy_trainer.train_dummy"})
        job_db.create_job({"_target_": "dr_exp.training.dummy_trainer.train_dummy"})
        
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs"
        )
        
        # Mock some workers
        launcher.processes["worker1"] = Mock(poll=lambda: None)
        launcher.worker_restarts["worker1"] = 2
        
        launcher.write_status()
        
        status_file = launcher.control_dir / f"status_{launcher.slurm_job_id}.json"
        assert status_file.exists()
        
        status = json.loads(status_file.read_text())
        assert status["launcher"]["running"] == False
        assert status["workers"]["worker1"] == "running"
        assert status["restarts"]["worker1"] == 2
        assert status["jobs"]["queued"] == 2
        


def test_graceful_shutdown():
    """Test graceful shutdown behavior."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs"
        )
        
        # Mock processes
        mock_process1 = Mock()
        mock_process1.pid = 1234
        mock_process1.poll.return_value = None
        
        mock_process2 = Mock()
        mock_process2.pid = 5678
        mock_process2.poll.return_value = None
        
        launcher.processes = {
            "worker1": mock_process1,
            "worker2": mock_process2
        }
        
        with patch('os.killpg') as mock_killpg:
            with patch('os.getpgid', side_effect=lambda pid: pid):
                launcher.stop()
        
        # Should have sent SIGTERM to both
        assert mock_killpg.call_count >= 2
        assert launcher.running == False
        


def test_runtime_limits():
    """Test runtime limit enforcement."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        # Create launcher with very short runtime
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs",
            max_runtime_hours=0.0001  # Very short for testing
        )
        
        # Backdate start time
        launcher.start_time = time.time() - 1000
        
        # Mock the stop method
        launcher.stop = Mock()
        
        # Simulate one loop iteration
        launcher.running = True
        
        # Should detect timeout and call stop
        with patch('time.sleep'):
            # Run one iteration of the main loop
            try:
                launcher.run()
            except:
                pass
        
        launcher.stop.assert_called()
        


```

## Validation
```bash
# Run the test with pytest
pt tests/implementation/test_step_2_7.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_2_7.py::test_launcher_init PASSED
# tests/implementation/test_step_2_7.py::test_gpu_discovery PASSED
# tests/implementation/test_step_2_7.py::test_worker_spawning PASSED
# tests/implementation/test_step_2_7.py::test_health_monitoring PASSED
# tests/implementation/test_step_2_7.py::test_control_files PASSED
# tests/implementation/test_step_2_7.py::test_status_writing PASSED
# tests/implementation/test_step_2_7.py::test_graceful_shutdown PASSED
# tests/implementation/test_step_2_7.py::test_runtime_limits PASSED
# ============================== 8 passed in X.XXs ===============================

# Verify code quality (runs ruff linting/formatting + mypy type checks)
ckdr

# Expected: All checks passed!

# Add launcher command to CLI registry
# Update src/dr_exp/cli/command_groups.py to include:
# from .commands.launcher import launcher
# system_group.add_command(launcher)
```

## Common Mistakes
- DO NOT: Try to manage GPU allocation yourself - use CUDA_VISIBLE_DEVICES
- DO NOT: Create complex worker coordination - let JobDB handle it
- DO NOT: Forget to handle SIGTERM for SLURM graceful shutdown
- DO NOT: Leave zombie processes - use process groups
- DO NOT: Exceed memory limits - enforce limits per worker if needed

## Next Step
Proceed to Step 2.8: Config Sweeps