# Step 2.6: Training Integration

## Goal (1 sentence)
Create training adapters for test and DeconCNN trainers with StructuredLogger integration for metrics tracking.

## Prerequisites
- [ ] Step 2.5 completed and validated
- [ ] Worker and CLI fully functional
- [ ] test_step_2_5.py passes

## Implementation

### 1. Create src/dr_exp/logging/__init__.py
```python
# Empty file to make this a package
```

### 2. Create src/dr_exp/logging/structured_logger.py
```python
"""Structured logging for ML experiments."""
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union
from datetime import datetime
from contextlib import contextmanager


class StructuredLogger:
    """Logger that writes structured data (metrics, configs, etc.) to files."""
    
    def __init__(self, log_dir: Union[str, Path], job_id: str, worker_id: str):
        """Initialize structured logger.
        
        Args:
            log_dir: Directory to write logs to
            job_id: Job ID for this run
            worker_id: Worker ID running this job
        """
        self.log_dir = Path(log_dir)
        self.job_id = job_id
        self.worker_id = worker_id
        
        # Ensure directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.metrics_file = self.log_dir / "metrics.jsonl"
        self.config_file = self.log_dir / "config.json"
        self.metadata_file = self.log_dir / "metadata.json"
        self.events_file = self.log_dir / "events.jsonl"
        
        # Write initial metadata
        self._write_metadata()
    
    def _write_metadata(self):
        """Write job metadata."""
        metadata = {
            "job_id": self.job_id,
            "worker_id": self.worker_id,
            "started_at": datetime.utcnow().isoformat(),
            "log_version": "1.0"
        }
        
        with open(self.metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)
    
    def log_config(self, config: Dict[str, Any]):
        """Log the configuration used for this run.
        
        Args:
            config: Configuration dictionary
        """
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)
    
    def log_metrics(self, metrics: Dict[str, Any], step: Optional[int] = None):
        """Log metrics for a training step.
        
        Args:
            metrics: Dictionary of metric values
            step: Optional step number (epoch, iteration, etc.)
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "step": step,
            "metrics": metrics
        }
        
        with open(self.metrics_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def log_event(self, event_type: str, data: Optional[Dict[str, Any]] = None):
        """Log a training event (start, end, checkpoint, etc.).
        
        Args:
            event_type: Type of event
            data: Optional event data
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "data": data or {}
        }
        
        with open(self.events_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def log_artifact(self, artifact_path: Path, artifact_type: str, 
                    metadata: Optional[Dict[str, Any]] = None):
        """Log that an artifact was created.
        
        Args:
            artifact_path: Path to the artifact
            artifact_type: Type of artifact (model, plot, etc.)
            metadata: Optional metadata about the artifact
        """
        self.log_event("artifact_created", {
            "path": str(artifact_path),
            "type": artifact_type,
            "metadata": metadata or {}
        })
    
    @contextmanager
    def phase(self, phase_name: str):
        """Context manager for logging training phases.
        
        Args:
            phase_name: Name of the phase (train, eval, etc.)
        """
        self.log_event(f"{phase_name}_start")
        try:
            yield
        finally:
            self.log_event(f"{phase_name}_end")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the logged data.
        
        Returns:
            Summary dictionary
        """
        summary = {
            "job_id": self.job_id,
            "worker_id": self.worker_id,
            "metrics_entries": 0,
            "events_entries": 0,
            "final_metrics": None
        }
        
        # Count metrics entries and get final
        if self.metrics_file.exists():
            with open(self.metrics_file, "r") as f:
                lines = f.readlines()
                summary["metrics_entries"] = len(lines)
                if lines:
                    last_entry = json.loads(lines[-1])
                    summary["final_metrics"] = last_entry.get("metrics", {})
        
        # Count events
        if self.events_file.exists():
            with open(self.events_file, "r") as f:
                summary["events_entries"] = sum(1 for _ in f)
        
        return summary
```

### 3. Create src/dr_exp/trainers/decon_trainer.py
```python
"""DeconCNN integration for dr_exp."""
from pathlib import Path
from typing import Dict, Any, Optional

from ..logging.structured_logger import StructuredLogger


def train_classification(
    job_id: str,
    worker_id: str,
    storage_path: str,
    model: Dict[str, Any],
    optim: Dict[str, Any],
    epochs: int = 100,
    batch_size: int = 128,
    data_path: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Train a classification model using deconCNN.
    
    This is a wrapper that adapts deconCNN's training to dr_exp's interface.
    
    Args:
        job_id: Job ID (injected by worker)
        worker_id: Worker ID (injected by worker)
        storage_path: Path to store artifacts (injected by worker)
        model: Model configuration
        optim: Optimizer configuration
        epochs: Number of epochs
        batch_size: Batch size
        data_path: Path to dataset
        **kwargs: Additional training arguments
        
    Returns:
        Dictionary with training results
    """
    # Initialize logger
    logger = StructuredLogger(storage_path, job_id, worker_id)
    
    # Log configuration
    config = {
        "model": model,
        "optim": optim,
        "epochs": epochs,
        "batch_size": batch_size,
        "data_path": data_path,
        **kwargs
    }
    logger.log_config(config)
    
    try:
        # Import deconCNN components (would be real imports in production)
        # from deconCNN.models import build_model
        # from deconCNN.data import build_dataloader
        # from deconCNN.trainer import Trainer
        
        # For testing, we'll simulate the training
        print(f"DeconCNN trainer starting for job {job_id}")
        print(f"Model: {model}")
        print(f"Optimizer: {optim}")
        print(f"Epochs: {epochs}, Batch size: {batch_size}")
        
        # Simulate training with metrics
        logger.log_event("training_start")
        
        best_accuracy = 0.0
        for epoch in range(epochs):
            # Simulate epoch metrics
            train_loss = 1.0 / (epoch + 1) + 0.1
            train_acc = min(0.99, epoch / epochs + 0.05)
            val_loss = train_loss + 0.05
            val_acc = train_acc - 0.02
            
            # Log metrics
            metrics = {
                "epoch": epoch,
                "train_loss": train_loss,
                "train_accuracy": train_acc,
                "val_loss": val_loss,
                "val_accuracy": val_acc,
                "learning_rate": optim.get("lr", 0.001) * (0.95 ** epoch)
            }
            logger.log_metrics(metrics, step=epoch)
            
            # Track best
            if val_acc > best_accuracy:
                best_accuracy = val_acc
                # Save checkpoint
                checkpoint_path = Path(storage_path) / f"checkpoint_epoch_{epoch}.pt"
                checkpoint_path.write_text(f"Mock checkpoint at epoch {epoch}")
                logger.log_artifact(checkpoint_path, "checkpoint", {"epoch": epoch, "val_acc": val_acc})
        
        # Save final model
        model_path = Path(storage_path) / "model_final.pt"
        model_path.write_text(f"Mock final model for {model}")
        logger.log_artifact(model_path, "model", {"epochs_trained": epochs})
        
        logger.log_event("training_complete")
        
        # Get summary
        summary = logger.get_summary()
        
        return {
            "metrics": {
                "final_train_loss": summary["final_metrics"].get("train_loss"),
                "final_train_accuracy": summary["final_metrics"].get("train_accuracy"),
                "final_val_loss": summary["final_metrics"].get("val_loss"),
                "final_val_accuracy": summary["final_metrics"].get("val_accuracy"),
                "best_val_accuracy": best_accuracy,
                "total_epochs": epochs
            },
            "artifacts": {
                "model_path": str(model_path),
                "metrics_path": str(logger.metrics_file),
                "config_path": str(logger.config_file)
            }
        }
        
    except Exception as e:
        logger.log_event("training_failed", {"error": str(e)})
        raise


def train_autoencoder(
    job_id: str,
    worker_id: str,
    storage_path: str,
    model: Dict[str, Any],
    optim: Dict[str, Any],
    epochs: int = 100,
    batch_size: int = 128,
    reconstruction_weight: float = 1.0,
    **kwargs
) -> Dict[str, Any]:
    """Train an autoencoder model using deconCNN.
    
    Args:
        job_id: Job ID (injected by worker)
        worker_id: Worker ID (injected by worker)
        storage_path: Path to store artifacts (injected by worker)
        model: Model configuration
        optim: Optimizer configuration
        epochs: Number of epochs
        batch_size: Batch size
        reconstruction_weight: Weight for reconstruction loss
        **kwargs: Additional training arguments
        
    Returns:
        Dictionary with training results
    """
    # Initialize logger
    logger = StructuredLogger(storage_path, job_id, worker_id)
    
    # Log configuration
    config = {
        "model": model,
        "optim": optim,
        "epochs": epochs,
        "batch_size": batch_size,
        "reconstruction_weight": reconstruction_weight,
        **kwargs
    }
    logger.log_config(config)
    
    # Similar training loop but for autoencoder
    logger.log_event("training_start", {"model_type": "autoencoder"})
    
    for epoch in range(min(epochs, 5)):  # Limit for testing
        metrics = {
            "epoch": epoch,
            "reconstruction_loss": 0.5 / (epoch + 1),
            "latent_loss": 0.1 / (epoch + 1),
            "total_loss": 0.6 / (epoch + 1)
        }
        logger.log_metrics(metrics, step=epoch)
    
    # Save model
    model_path = Path(storage_path) / "autoencoder_final.pt"
    model_path.write_text("Mock autoencoder model")
    logger.log_artifact(model_path, "model")
    
    logger.log_event("training_complete")
    
    summary = logger.get_summary()
    
    return {
        "metrics": summary["final_metrics"],
        "artifacts": {
            "model_path": str(model_path),
            "metrics_path": str(logger.metrics_file)
        }
    }
```

### 4. Create tests/implementation/test_step_2_6.py
```python
"""Test training integration."""
import tempfile
import json
import pytest
from pathlib import Path

from src.dr_exp.core.job_db import JobDB
from src.dr_exp.worker.base import Worker
from src.dr_exp.logging.structured_logger import StructuredLogger


def test_structured_logger():
    """Test structured logger functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = StructuredLogger(tmpdir, "test_job", "test_worker")
        
        # Log config
        config = {
            "model": {"name": "resnet18"},
            "epochs": 10
        }
        logger.log_config(config)
        
        # Log metrics
        for i in range(5):
            logger.log_metrics({
                "loss": 1.0 / (i + 1),
                "accuracy": i / 5
            }, step=i)
        
        # Log events
        logger.log_event("checkpoint_saved", {"epoch": 3})
        
        # Use phase context
        with logger.phase("validation"):
            logger.log_metrics({"val_loss": 0.5})
        
        # Verify files created
        assert logger.config_file.exists()
        assert logger.metrics_file.exists()
        assert logger.events_file.exists()
        assert logger.metadata_file.exists()
        
        # Verify content
        with open(logger.config_file) as f:
            saved_config = json.load(f)
            assert saved_config == config
        
        # Check metrics entries
        with open(logger.metrics_file) as f:
            lines = f.readlines()
            assert len(lines) == 6  # 5 + 1 validation
            
            first_entry = json.loads(lines[0])
            assert first_entry["step"] == 0
            assert first_entry["metrics"]["loss"] == 1.0
        
        # Check events
        with open(logger.events_file) as f:
            events = [json.loads(line) for line in f]
            event_types = [e["event_type"] for e in events]
            assert "checkpoint_saved" in event_types
            assert "validation_start" in event_types
            assert "validation_end" in event_types
        
        # Test summary
        summary = logger.get_summary()
        assert summary["metrics_entries"] == 6
        assert summary["events_entries"] == 3
        assert summary["final_metrics"]["val_loss"] == 0.5
        


def test_decon_classification_trainer():
    """Test deconCNN classification trainer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create job
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        config = {
            "_target_": "src.dr_exp.trainers.decon_trainer.train_classification",
            "model": {
                "architecture": "resnet18",
                "num_classes": 10
            },
            "optim": {
                "name": "adamw",
                "lr": 0.001
            },
            "epochs": 5,
            "batch_size": 32
        }
        
        job_id = job_db.create_job(config)
        
        # Run with worker
        worker = Worker(job_db=job_db, worker_id="test_worker")
        status = worker.run_one_job()
        
        assert status == "completed"
        
        # Verify job results
        job = job_db.get_job(job_id)
        assert job["status"] == "completed"
        assert "final_metrics" in job
        
        metrics = job["final_metrics"]
        assert "final_train_accuracy" in metrics
        assert "final_val_accuracy" in metrics
        assert "best_val_accuracy" in metrics
        assert metrics["total_epochs"] == 5
        
        # Verify artifacts
        storage_path = job_db.get_storage_path(job_id)
        assert (storage_path / "model_final.pt").exists()
        assert (storage_path / "metrics.jsonl").exists()
        assert (storage_path / "config.json").exists()
        assert (storage_path / "events.jsonl").exists()
        
        # Check metrics file content
        with open(storage_path / "metrics.jsonl") as f:
            lines = f.readlines()
            assert len(lines) == 5  # One per epoch
            
            # Check progression
            first_metrics = json.loads(lines[0])["metrics"]
            last_metrics = json.loads(lines[-1])["metrics"]
            assert last_metrics["train_accuracy"] > first_metrics["train_accuracy"]
        


def test_decon_autoencoder_trainer():
    """Test deconCNN autoencoder trainer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        config = {
            "_target_": "src.dr_exp.trainers.decon_trainer.train_autoencoder",
            "model": {
                "encoder_dims": [784, 256, 64],
                "decoder_dims": [64, 256, 784]
            },
            "optim": {
                "name": "adam",
                "lr": 0.0001
            },
            "epochs": 10,
            "reconstruction_weight": 2.0
        }
        
        job_id = job_db.create_job(config)
        
        # Run with worker
        worker = Worker(job_db=job_db, worker_id="test_worker")
        status = worker.run_one_job()
        
        assert status == "completed"
        
        # Verify results
        job = job_db.get_job(job_id)
        metrics = job["final_metrics"]
        assert "reconstruction_loss" in metrics
        assert "total_loss" in metrics
        
        # Verify model saved
        storage_path = job_db.get_storage_path(job_id)
        assert (storage_path / "autoencoder_final.pt").exists()
        


def test_trainer_error_handling():
    """Test trainer error handling and logging."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create a config that will cause an error
        config = {
            "_target_": "src.dr_exp.trainers.test_trainer.train",
            "epochs": 5,
            "fail_rate": 1.0  # Will cause failure
        }
        
        job_id = job_db.create_job(config)
        
        # Run with worker
        worker = Worker(job_db=job_db, worker_id="test_worker")
        status = worker.run_one_job()
        
        assert status == "failed"
        
        # Verify error captured
        job = job_db.get_job(job_id)
        assert job["status"] == "failed"
        assert "Simulated training failure" in job["error"]
        
        # Verify error artifact
        storage_path = job_db.get_storage_path(job_id)
        assert (storage_path / "error.txt").exists()
        
        error_content = (storage_path / "error.txt").read_text()
        assert "RuntimeError" in error_content
        assert "Traceback" in error_content
        


def test_worker_artifact_discovery():
    """Test that worker discovers and queues all artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        config = {
            "_target_": "src.dr_exp.trainers.decon_trainer.train_classification",
            "model": {"architecture": "resnet50"},
            "optim": {"lr": 0.01},
            "epochs": 3
        }
        
        job_id = job_db.create_job(config)
        
        # Track what gets queued
        queued_files = []
        
        # Custom worker that tracks sync queue
        class TrackingWorker(Worker):
            def add_artifact_to_sync(self, job_id, file_path, file_type, metadata=None):
                queued_files.append((Path(file_path).name, file_type))
                super().add_artifact_to_sync(job_id, file_path, file_type, metadata)
        
        worker = TrackingWorker(job_db=job_db, worker_id="tracking_worker")
        worker.run_one_job()
        
        # Check what was queued
        file_types = {ft for _, ft in queued_files}
        assert "metrics" in file_types
        assert "model" in file_types
        assert "logs" in file_types
        
        # Verify specific files
        file_names = {fn for fn, _ in queued_files}
        assert "metrics.jsonl" in file_names
        assert "model_final.pt" in file_names
        assert any("checkpoint" in fn for fn in file_names)
        


def test_full_integration():
    """Test complete integration from job submission to completion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from click.testing import CliRunner
        from src.dr_exp.cli.main import cli
        
        runner = CliRunner()
        
        # Initialize experiment
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'integration_test',
            'init'
        ])
        assert result.exit_code == 0
        
        # Create config file
        config_file = Path(tmpdir) / 'train_config.yaml'
        config_file.write_text("""
_target_: src.dr_exp.trainers.decon_trainer.train_classification
model:
  architecture: efficientnet_b0
  num_classes: 100
optim:
  name: sgd
  lr: 0.1
  momentum: 0.9
epochs: 10
batch_size: 256
""")
        
        # Submit job
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'integration_test',
            'submit', str(config_file),
            '--priority', '800'
        ])
        assert result.exit_code == 0
        job_output = result.output
        
        # Extract job ID from output
        import re
        match = re.search(r'Created job: ([\w-]+)', job_output)
        assert match
        job_id = match.group(1)
        
        # Run worker
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'integration_test',
            'worker',
            '--worker-id', 'integration_worker',
            '--max-jobs', '1',
            '--no-sync'
        ])
        assert result.exit_code == 0
        assert "'completed': 1" in result.output
        
        # Check job status
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'integration_test',
            'list',
            '--status', 'completed'
        ])
        assert result.exit_code == 0
        assert job_id in result.output
        
        # Validate artifacts exist
        job_db = JobDB(base_path=tmpdir, experiment_name='integration_test')
        storage_path = job_db.get_storage_path(job_id)
        
        expected_files = [
            "model_final.pt",
            "metrics.jsonl",
            "config.json",
            "metadata.json",
            "events.jsonl"
        ]
        
        for filename in expected_files:
            assert (storage_path / filename).exists(), f"Missing {filename}"
        
        # Check final metrics
        job = job_db.get_job(job_id)
        assert job["final_metrics"]["total_epochs"] == 10
        assert job["final_metrics"]["final_val_accuracy"] > 0
        


```

## Validation
```bash
# Run the test with pytest
pt tests/implementation/test_step_2_6.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_2_6.py::test_structured_logger PASSED
# tests/implementation/test_step_2_6.py::test_decon_classification_trainer PASSED
# tests/implementation/test_step_2_6.py::test_decon_autoencoder_trainer PASSED
# tests/implementation/test_step_2_6.py::test_trainer_error_handling PASSED
# tests/implementation/test_step_2_6.py::test_worker_artifact_discovery PASSED
# tests/implementation/test_step_2_6.py::test_full_integration PASSED
# ============================== 6 passed in X.XXs ===============================

# Run ALL Phase 2 tests to ensure nothing broke
pt tests/implementation/test_step_2_1.py -v
pt tests/implementation/test_step_2_2.py -v
pt tests/implementation/test_step_2_3.py -v
pt tests/implementation/test_step_2_4.py -v
pt tests/implementation/test_step_2_5.py -v

# Verify code quality (runs ruff linting/formatting + mypy type checks)
ckdr

# Expected: All checks passed!

# Test end-to-end workflow
dr_exp --base-path /tmp/e2e --experiment final_test init
echo '_target_: src.dr_exp.trainers.decon_trainer.train_classification
model: {architecture: resnet18}
optim: {lr: 0.001}
epochs: 5' > /tmp/e2e/test.yaml
dr_exp --base-path /tmp/e2e --experiment final_test submit /tmp/e2e/test.yaml
dr_exp --base-path /tmp/e2e --experiment final_test worker --worker-id test --max-jobs 1
```

## Common Mistakes
- DO NOT: Import real ML libraries in test code - keep tests isolated
- DO NOT: Write large amounts of data in tests - use small epochs/batches
- DO NOT: Forget to log both successes and failures
- DO NOT: Make the logger too complex - it should be simple to use
- DO NOT: Tightly couple trainers to specific ML frameworks

## Phase 2 Complete! 🎉

You have successfully implemented:
- Basic worker that executes jobs using Hydra
- Sync queue with retry logic and persistence
- Worker with background sync and heartbeat threads
- Complete CLI with job management commands
- Training integration with structured logging
- Full end-to-end workflow from job submission to completion

The system can now:
- Submit jobs via CLI with configs
- Run workers that claim jobs by priority
- Execute training with full metrics logging
- Track artifacts and queue them for sync
- Monitor and manage jobs (kill, boost, recover)
- Handle failures gracefully with error logging

## Next Step
Proceed to Phase 3, Step 3.1: Database Schema