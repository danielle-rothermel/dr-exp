"""Test sync queue functionality."""

import tempfile
import time
import json
from pathlib import Path
from datetime import datetime, timedelta

from dr_exp.sync.queue import SyncQueue, SyncItem


def test_sync_queue_basic() -> None:
    """Test basic sync queue operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        queue_dir = Path(tmpdir) / "sync_queue"
        queue = SyncQueue(queue_dir)

        # Create a test file
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("Test content")

        # Add item to queue
        item = SyncItem(
            id="sync_1",
            job_id="job_1",
            file_path=str(test_file),
            file_type="test",
            metadata={"key": "value"},
            created_at=datetime.utcnow().isoformat(),
        )

        queue_file = queue.add_item(item)
        assert Path(queue_file).exists()

        # Item should have checksum and size
        with Path(queue_file).open() as f:
            data = json.load(f)
            assert data["checksum"] is not None
            assert data["size_bytes"] == len("Test content")

        # Get pending items
        pending = queue.get_pending_items()
        assert len(pending) == 1
        assert pending[0].id == "sync_1"
        assert pending[0].status == "pending"
        assert pending[0].attempts == 0

        # Get stats
        stats = queue.get_stats()
        assert stats["pending"] == 1
        assert stats["total"] == 1


def test_sync_queue_processing() -> None:
    """Test processing items in the queue."""
    with tempfile.TemporaryDirectory() as tmpdir:
        queue_dir = Path(tmpdir) / "sync_queue"
        queue = SyncQueue(queue_dir)

        # Add multiple items
        for i in range(5):
            test_file = Path(tmpdir) / f"file_{i}.txt"
            test_file.write_text(f"Content {i}")

            item = SyncItem(
                id=f"sync_{i}",
                job_id=f"job_{i}",
                file_path=str(test_file),
                file_type="test",
                metadata={"index": i},
                created_at=datetime.utcnow().isoformat(),
            )
            queue.add_item(item)
            time.sleep(0.001)  # Ensure different timestamps

        # Define sync function
        processed = []

        def mock_sync(item: SyncItem) -> None:
            processed.append(item.id)
            # Simulate upload
            time.sleep(0.01)

        # Process batch
        results = queue.process_queue(mock_sync, batch_size=3)

        assert results["success"] == 3
        assert results["failed"] == 0
        assert results["skipped"] == 2
        assert len(processed) == 3

        # Verify completed items moved to history
        stats = queue.get_stats()
        assert stats["pending"] == 2
        assert stats["completed"] == 3

        # Verify history file
        assert queue.history_file.exists()
        with queue.history_file.open() as f:
            lines = f.readlines()
            assert len(lines) == 3


def test_sync_queue_retry() -> None:
    """Test retry logic with exponential backoff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        queue_dir = Path(tmpdir) / "sync_queue"
        queue = SyncQueue(queue_dir, max_retries=3)

        # Add item
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("Test")

        item = SyncItem(
            id="retry_test",
            job_id="job_1",
            file_path=str(test_file),
            file_type="test",
            metadata={},
            created_at=datetime.utcnow().isoformat(),
        )
        queue.add_item(item)

        # First attempt fails
        success = queue.mark_attempt("retry_test", "Network error")
        assert success

        # Check item status
        items = queue.get_pending_items()
        assert len(items) == 0  # Not available immediately (backoff)

        # Check the raw data
        for queue_file in queue_dir.glob("*_retry_test.json"):
            with Path(queue_file).open() as f:
                data = json.load(f)
                assert data["attempts"] == 1
                assert data["error"] == "Network error"
                assert data["status"] == "pending"  # Still pending

        # Simulate time passing (bypass backoff for testing)
        queue.update_item(
            "retry_test",
            {"last_attempt": (datetime.utcnow() - timedelta(minutes=5)).isoformat()},
        )

        # Now available again
        items = queue.get_pending_items()
        assert len(items) == 1

        # Fail until max retries
        for i in range(2):  # 2 more attempts to reach max
            queue.mark_attempt("retry_test", f"Error {i + 2}")
            queue.update_item(
                "retry_test",
                {
                    "last_attempt": (
                        datetime.utcnow() - timedelta(minutes=5)
                    ).isoformat()
                },
            )

        # Should be marked as failed now
        items = queue.get_pending_items()
        assert len(items) == 0

        # Check final status
        for queue_file in queue_dir.glob("*_retry_test.json"):
            with Path(queue_file).open() as f:
                data = json.load(f)
                assert data["attempts"] == 3
                assert data["status"] == "failed"


def test_sync_queue_complete() -> None:
    """Test completing items."""
    with tempfile.TemporaryDirectory() as tmpdir:
        queue_dir = Path(tmpdir) / "sync_queue"
        queue = SyncQueue(queue_dir)

        # Add item
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("Test")

        item = SyncItem(
            id="complete_test",
            job_id="job_1",
            file_path=str(test_file),
            file_type="test",
            metadata={},
            created_at=datetime.utcnow().isoformat(),
        )
        queue.add_item(item)

        # Complete the item
        success = queue.complete_item("complete_test")
        assert success

        # Should not be in pending
        items = queue.get_pending_items()
        assert len(items) == 0

        # Should be in history
        assert queue.history_file.exists()
        with queue.history_file.open() as f:
            line = f.readline()
            data = json.loads(line)
            assert data["id"] == "complete_test"
            assert data["status"] == "completed"
            assert data["completed_at"] is not None

        # Queue file should be removed
        queue_files = list(queue_dir.glob("*_complete_test.json"))
        assert len(queue_files) == 0


def test_sync_queue_ordering() -> None:
    """Test that items are processed in order."""
    with tempfile.TemporaryDirectory() as tmpdir:
        queue_dir = Path(tmpdir) / "sync_queue"
        queue = SyncQueue(queue_dir)

        # Add items with delays to ensure ordering
        ids = []
        for i in range(5):
            test_file = Path(tmpdir) / f"file_{i}.txt"
            test_file.write_text(f"Content {i}")

            item = SyncItem(
                id=f"order_{i}",
                job_id=f"job_{i}",
                file_path=str(test_file),
                file_type="test",
                metadata={"order": i},
                created_at=datetime.utcnow().isoformat(),
            )
            queue.add_item(item)
            ids.append(item.id)
            time.sleep(0.01)  # Ensure different timestamps

        # Get items - should be in order
        items = queue.get_pending_items()
        assert len(items) == 5

        # Verify order
        for i, item in enumerate(items):
            assert item.id == f"order_{i}"
            assert item.metadata["order"] == i


def test_sync_queue_error_handling() -> None:
    """Test handling sync errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        queue_dir = Path(tmpdir) / "sync_queue"
        queue = SyncQueue(queue_dir)

        # Add items
        for i in range(3):
            test_file = Path(tmpdir) / f"file_{i}.txt"
            test_file.write_text(f"Content {i}")

            item = SyncItem(
                id=f"error_{i}",
                job_id=f"job_{i}",
                file_path=str(test_file),
                file_type="test",
                metadata={},
                created_at=datetime.utcnow().isoformat(),
            )
            queue.add_item(item)

        # Sync function that fails for specific items
        def failing_sync(item: SyncItem) -> None:
            if "error_1" in item.id:
                raise ValueError("Simulated sync error")
            # Others succeed

        # Process queue
        results = queue.process_queue(failing_sync, batch_size=10)

        assert results["success"] == 2
        assert results["failed"] == 1

        # Check failed item
        for queue_file in queue_dir.glob("*_error_1.json"):
            with Path(queue_file).open() as f:
                data = json.load(f)
                assert data["attempts"] == 1
                assert "Simulated sync error" in data["error"]
                assert data["status"] == "pending"  # Can be retried
