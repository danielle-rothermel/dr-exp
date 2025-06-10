# Step 1.1: Basic JobDB Structure

## Goal (1 sentence)
Create the foundational JobDB class that can create and retrieve jobs from the filesystem.

## Prerequisites
- [ ] Clean working directory
- [ ] Python 3.10+ environment with `uv` installed
- [ ] Basic project structure created

## Implementation

### 1. Create src/dr_exp/core/__init__.py
```python
# Empty file to make this a package
```

### 2. Create src/dr_exp/core/job_db.py
```python
"""Simple file-based job database for ML experiments."""
import json
import os
import uuid
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class JobDB:
    """File-based job database with priority queue."""
    
    def __init__(self, base_path: str, experiment_name: str, validate: bool = True):
        """Initialize JobDB with base path and experiment name.
        
        Args:
            base_path: Base directory for all experiments (e.g., /scratch/users/jane/experiments)
            experiment_name: Name of this experiment (e.g., resnet_sweep)
            validate: Whether to validate directory structure exists
        """
        # Validate inputs
        assert base_path, "base_path cannot be empty"
        assert experiment_name, "experiment_name cannot be empty"
        assert "/" not in experiment_name, "experiment_name cannot contain '/'"
        
        self.base_path = Path(base_path)
        self.experiment_name = experiment_name
        self.experiment_path = self.base_path / experiment_name
        
        # Define directory structure
        self.jobs_dir = self.experiment_path / "jobs"
        self.storage_dir = self.experiment_path / "storage"
        self.sync_queue_dir = self.experiment_path / "sync_queue"
        self.logs_dir = self.experiment_path / "logs"
        self.control_dir = self.experiment_path / "control"
        
        if validate:
            # Check that experiment is initialized
            required_dirs = [
                self.jobs_dir,
                self.storage_dir,
                self.sync_queue_dir,
                self.logs_dir,
                self.control_dir
            ]
            
            missing = [d for d in required_dirs if not d.exists()]
            if missing:
                missing_names = [d.name for d in missing]
                raise RuntimeError(
                    f"Experiment not initialized. Missing directories: {missing_names}\n"
                    f"Run: dr_exp --base-path {base_path} --experiment {experiment_name} init"
                )
        else:
            # Create directories if they don't exist (for init command)
            for dir_path in [self.jobs_dir, self.storage_dir, self.sync_queue_dir, 
                           self.logs_dir, self.control_dir]:
                dir_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"JobDB initialized for experiment '{experiment_name}' at {self.experiment_path}")
    
    def create_job(self, config: Dict[str, Any], priority: int = 100) -> str:
        """Create a new job with given config and priority.
        
        Args:
            config: Job configuration dict (must include _target_ field)
            priority: Job priority (0-1000, higher runs first)
            
        Returns:
            job_id: Unique ID for the created job
        """
        # Validate priority
        assert 0 <= priority <= 1000, f"Priority must be 0-1000, got {priority}"
        
        # Validate _target_ exists
        assert "_target_" in config, "Config must include _target_ field"
        
        # Validate target is importable
        target = config["_target_"]
        module_path, func_name = target.rsplit('.', 1)
        try:
            import importlib
            importlib.import_module(module_path)
        except ImportError as e:
            assert False, f"Cannot import target module {module_path}: {e}"
        
        # Create job metadata
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "experiment_name": self.experiment_name,
            "config": config,
            "priority": priority,
            "status": "queued",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "attempts": 0,
            "worker_id": None,
            "error": None,
            "completed_at": None,
        }
        
        # Write to file
        job_path = self.jobs_dir / f"{job_id}.json"
        with open(job_path, "w") as f:
            json.dump(job_data, f, indent=2)
        
        logger.info(f"Created job {job_id} with priority {priority}")
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a job by ID.
        
        Args:
            job_id: Job ID to retrieve
            
        Returns:
            Job data dict or None if not found
        """
        job_path = self.jobs_dir / f"{job_id}.json"
        if not job_path.exists():
            return None
        
        with open(job_path, "r") as f:
            return json.load(f)
    
    def get_storage_path(self, job_id: str) -> Path:
        """Get the storage path for a job's artifacts.
        
        Args:
            job_id: Job ID
            
        Returns:
            Path object for job's storage directory
        """
        return self.storage_dir / f"run_{job_id}"
```

### 3. Create tests/implementation/test_step_1_1.py
```python
"""Test basic JobDB functionality."""
import tempfile
import shutil
import pytest
from pathlib import Path

from src.dr_exp.core.job_db import JobDB


def test_jobdb_basic():
    """Test creating and retrieving jobs."""
    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize JobDB without validation (like init command)
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        # Verify all directories created
        exp_path = Path(tmpdir) / "test_exp"
        assert (exp_path / "jobs").exists()
        assert (exp_path / "storage").exists()
        assert (exp_path / "sync_queue").exists()
        assert (exp_path / "logs").exists()
        assert (exp_path / "control").exists()
        
        # Create a job
        config = {
            "_target_": "dr_exp.training.dummy_trainer.train_dummy",
            "model": "resnet18",
            "lr": 0.001,
            "epochs": 10
        }
        job_id = job_db.create_job(config, priority=500)
        
        # Verify job file created
        assert (exp_path / "jobs" / f"{job_id}.json").exists()
        
        # Retrieve the job
        job = job_db.get_job(job_id)
        assert job is not None
        assert job["id"] == job_id
        assert job["experiment_name"] == "test_exp"
        assert job["config"] == config
        assert job["priority"] == 500
        assert job["status"] == "queued"
        assert job["worker_id"] is None
        
        # Test storage path
        storage_path = job_db.get_storage_path(job_id)
        assert storage_path == exp_path / "storage" / f"run_{job_id}"
        
        # Test validation mode
        try:
            # Delete a directory and try with validation=True
            shutil.rmtree(exp_path / "logs")
            job_db2 = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=True)
            assert False, "Should have failed"
        except RuntimeError as e:
            assert "Missing directories" in str(e)
            assert "logs" in str(e)
        
        # Test input validation
        try:
            # Missing _target_
            job_db.create_job({"model": "resnet"}, priority=100)
            assert False, "Should have failed"
        except AssertionError as e:
            assert "_target_" in str(e)
        
        try:
            # Invalid priority
            job_db.create_job(config, priority=1500)
            assert False, "Should have failed"
        except AssertionError as e:
            assert "Priority" in str(e)
        
        try:
            # Invalid target module
            bad_config = {"_target_": "nonexistent.module.train"}
            job_db.create_job(bad_config, priority=100)
            assert False, "Should have failed"
        except AssertionError as e:
            assert "Cannot import" in str(e)
```

## Validation
```bash
# Run the test with pytest
pt tests/implementation/test_step_1_1.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_1_1.py::test_jobdb_basic PASSED
# ============================== 1 passed in X.XXs ===============================

# Verify code quality (runs ruff linting/formatting + mypy type checks)
ckdr

# Expected: All checks passed!
```

## Common Mistakes
- DO NOT: Use abstract base classes or interfaces
- DO NOT: Add configuration files - pass parameters directly
- DO NOT: Use exceptions for validation - use assertions
- DO NOT: Add features not specified (no caching, no indexing, etc.)
- DO NOT: Forget to create parent directories with `parents=True`

## Next Step
Proceed to Step 1.2: Concurrent Job Claiming