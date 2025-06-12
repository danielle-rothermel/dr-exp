#!/usr/bin/env python3
"""Simple test to debug launcher behavior."""

import os
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, '/scratch/ddr8143/repos/dr_exp/src')

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Test imports
try:
    from dr_exp.core.job_db import JobDB
    from dr_exp.worker.launcher import WorkerLauncher
    print("✓ Imports successful")
except Exception as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test parameters
BASE_PATH = Path("/scratch/ddr8143/repos/dr_exp/test_launcher_simple")
EXPERIMENT = "debug"

# Initialize
try:
    exp_dir = BASE_PATH / EXPERIMENT
    exp_dir.mkdir(parents=True, exist_ok=True)
    
    # Create required directories
    (exp_dir / "jobs").mkdir(exist_ok=True)
    (exp_dir / "storage").mkdir(exist_ok=True)
    (exp_dir / "sync_queue").mkdir(exist_ok=True)
    (exp_dir / "logs").mkdir(exist_ok=True)
    (exp_dir / "control").mkdir(exist_ok=True)
    
    print(f"✓ Created experiment directory: {exp_dir}")
except Exception as e:
    print(f"✗ Failed to create directories: {e}")
    sys.exit(1)

# Initialize JobDB
try:
    job_db = JobDB(exp_dir)
    print("✓ JobDB initialized")
    
    # Submit a test job
    job_id = job_db.submit_job({
        "_target_": "dr_exp.trainers.test_trainer.test_train",
        "epochs": 1,
        "sleep_time": 5,
    }, priority=100)
    print(f"✓ Submitted test job: {job_id}")
    
    # Check job status
    jobs = job_db.list_jobs()
    print(f"✓ Total jobs: {len(jobs)}")
    print(f"  Queued: {len([j for j in jobs if j['status'] == 'queued'])}")
    
except Exception as e:
    print(f"✗ JobDB error: {e}")
    sys.exit(1)

# Test WorkerLauncher initialization
try:
    launcher = WorkerLauncher(
        job_db=job_db,
        experiment_name=EXPERIMENT,
        base_log_dir=exp_dir / "logs",
        workers_per_gpu=1,
        max_runtime_hours=0.1  # 6 minutes for testing
    )
    print("✓ WorkerLauncher initialized")
    
    # Check GPU discovery
    gpus = launcher.discover_gpus()
    print(f"✓ Discovered GPUs: {gpus}")
    
    # Try spawning a single worker
    print("\n--- Testing worker spawn ---")
    if gpus:
        gpu_id = gpus[0]
        print(f"Spawning worker on GPU {gpu_id}...")
    else:
        gpu_id = None
        print("Spawning CPU worker...")
    
    launcher.spawn_worker(gpu_id, 0)
    
    # Check if worker started
    import time
    time.sleep(2)
    health = launcher.check_worker_health()
    print(f"Worker health: {health}")
    
    # Clean up
    launcher.stop()
    print("✓ Launcher stopped")
    
except Exception as e:
    print(f"✗ Launcher error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✓ All tests passed!")