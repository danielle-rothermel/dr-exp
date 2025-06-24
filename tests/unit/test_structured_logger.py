"""Unit tests for StructuredLogger functionality."""

import tempfile
import json

from dr_exp.logging.structured_logger import StructuredLogger


def test_structured_logger() -> None:
    """Test structured logger functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = StructuredLogger(tmpdir, "test_job", "test_worker")

        # Log config
        config = {"model": {"name": "resnet18"}, "epochs": 10}
        logger.log_config(config)

        # Log metrics
        for i in range(5):
            logger.log_metrics({"loss": 1.0 / (i + 1), "accuracy": i / 5}, step=i)

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
        with logger.config_file.open() as f:
            saved_config = json.load(f)
            assert saved_config == config

        # Check metrics entries
        with logger.metrics_file.open() as f:
            lines = f.readlines()
            assert len(lines) == 6  # 5 + 1 validation

            first_entry = json.loads(lines[0])
            assert first_entry["step"] == 0
            assert first_entry["metrics"]["loss"] == 1.0

        # Check events
        with logger.events_file.open() as f:
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
