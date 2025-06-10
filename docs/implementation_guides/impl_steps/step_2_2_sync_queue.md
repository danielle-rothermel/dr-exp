# Step 2.2: Sync Queue Implementation

## Goal (1 sentence)
Create a SyncQueue class that manages pending file uploads with persistence and retry logic.

## Prerequisites
- [ ] Step 2.1 completed and validated
- [ ] Required files exist: src/dr_exp/worker/base.py
- [ ] test_step_2_1.py passes

## Implementation

### 1. Create src/dr_exp/sync/__init__.py
```python
# Empty file to make this a package
```

### 2. Create src/dr_exp/sync/queue.py
```python
"""Sync queue for managing file uploads."""
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict


@dataclass
class SyncItem:
    """Represents an item to be synced."""
    id: str
    job_id: str
    file_path: str
    file_type: str
    metadata: Dict[str, Any]
    created_at: str
    status: str = "pending"
    attempts: int = 0
    last_attempt: Optional[str] = None
    error: Optional[str] = None
    completed_at: Optional[str] = None
    checksum: Optional[str] = None
    size_bytes: Optional[int] = None


class SyncQueue:
    """Manages queue of files to sync."""
    
    def __init__(self, queue_dir: Path, max_retries: int = 3):
        """Initialize sync queue.
        
        Args:
            queue_dir: Directory to store queue files
            max_retries: Maximum retry attempts per item
        """
        self.queue_dir = Path(queue_dir)
        self.max_retries = max_retries
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        
        # History file to track completed items
        self.history_file = self.queue_dir / "_sync_history.jsonl"
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Hex string of checksum
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def add_item(self, sync_item: SyncItem) -> str:
        """Add an item to the sync queue.
        
        Args:
            sync_item: Item to add
            
        Returns:
            Queue file path
        """
        # Calculate file metadata if not provided
        file_path = Path(sync_item.file_path)
        if file_path.exists():
            if sync_item.checksum is None:
                sync_item.checksum = self._calculate_checksum(file_path)
            if sync_item.size_bytes is None:
                sync_item.size_bytes = file_path.stat().st_size
        
        # Write to queue with timestamp prefix for ordering
        timestamp = int(time.time() * 1000000)  # Microseconds
        queue_file = self.queue_dir / f"{timestamp}_{sync_item.id}.json"
        
        with open(queue_file, "w") as f:
            json.dump(asdict(sync_item), f, indent=2)
        
        return str(queue_file)
    
    def get_pending_items(self, limit: Optional[int] = None) -> List[SyncItem]:
        """Get pending items from the queue.
        
        Args:
            limit: Maximum number of items to return
            
        Returns:
            List of pending sync items (oldest first)
        """
        items = []
        
        # Read all queue files
        queue_files = sorted(self.queue_dir.glob("*.json"))
        
        for queue_file in queue_files:
            # Skip history file
            if queue_file.name.startswith("_"):
                continue
            
            try:
                with open(queue_file, "r") as f:
                    data = json.load(f)
                    
                # Skip if not pending or too many attempts
                if data["status"] != "pending":
                    continue
                if data["attempts"] >= self.max_retries:
                    continue
                
                # Check retry delay (exponential backoff)
                if data["attempts"] > 0 and data.get("last_attempt"):
                    last_attempt = datetime.fromisoformat(data["last_attempt"])
                    retry_delay = timedelta(seconds=60 * (2 ** (data["attempts"] - 1)))
                    if datetime.utcnow() < last_attempt + retry_delay:
                        continue
                
                items.append(SyncItem(**data))
                
                if limit and len(items) >= limit:
                    break
                    
            except (json.JSONDecodeError, KeyError):
                # Skip corrupted files
                continue
        
        return items
    
    def update_item(self, item_id: str, updates: Dict[str, Any]) -> bool:
        """Update a sync item in the queue.
        
        Args:
            item_id: ID of item to update
            updates: Fields to update
            
        Returns:
            True if updated, False if not found
        """
        # Find the queue file
        for queue_file in self.queue_dir.glob(f"*_{item_id}.json"):
            try:
                with open(queue_file, "r") as f:
                    data = json.load(f)
                
                # Apply updates
                data.update(updates)
                
                # Write back
                with open(queue_file, "w") as f:
                    json.dump(data, f, indent=2)
                
                return True
                
            except (json.JSONDecodeError, IOError):
                continue
        
        return False
    
    def mark_attempt(self, item_id: str, error: Optional[str] = None) -> bool:
        """Mark a sync attempt (success or failure).
        
        Args:
            item_id: ID of item that was attempted
            error: Error message if failed, None if successful
            
        Returns:
            True if updated
        """
        now = datetime.utcnow().isoformat()
        
        if error:
            # Failed attempt
            updates = {
                "attempts": None,  # Will be incremented below
                "last_attempt": now,
                "error": error
            }
            
            # Get current attempts to increment
            for queue_file in self.queue_dir.glob(f"*_{item_id}.json"):
                try:
                    with open(queue_file, "r") as f:
                        data = json.load(f)
                        updates["attempts"] = data.get("attempts", 0) + 1
                        
                        # Mark as failed if too many attempts
                        if updates["attempts"] >= self.max_retries:
                            updates["status"] = "failed"
                    break
                except:
                    continue
        else:
            # Successful attempt
            updates = {
                "status": "completed",
                "completed_at": now,
                "error": None
            }
        
        return self.update_item(item_id, updates)
    
    def complete_item(self, item_id: str) -> bool:
        """Mark an item as successfully synced and move to history.
        
        Args:
            item_id: ID of completed item
            
        Returns:
            True if completed
        """
        # Find and read the queue file
        for queue_file in self.queue_dir.glob(f"*_{item_id}.json"):
            try:
                with open(queue_file, "r") as f:
                    data = json.load(f)
                
                # Update status
                data["status"] = "completed"
                data["completed_at"] = datetime.utcnow().isoformat()
                data["error"] = None
                
                # Append to history
                with open(self.history_file, "a") as f:
                    f.write(json.dumps(data) + "\n")
                
                # Remove from queue
                queue_file.unlink()
                
                return True
                
            except (json.JSONDecodeError, IOError):
                continue
        
        return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics.
        
        Returns:
            Dict with counts by status
        """
        stats = {
            "pending": 0,
            "failed": 0,
            "completed": 0,
            "total": 0
        }
        
        # Count queue files
        for queue_file in self.queue_dir.glob("*.json"):
            if queue_file.name.startswith("_"):
                continue
            
            try:
                with open(queue_file, "r") as f:
                    data = json.load(f)
                    status = data.get("status", "pending")
                    if status in stats:
                        stats[status] += 1
                    stats["total"] += 1
            except:
                continue
        
        # Count history entries
        if self.history_file.exists():
            with open(self.history_file, "r") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        if data.get("status") == "completed":
                            stats["completed"] += 1
                            stats["total"] += 1
                    except:
                        continue
        
        return stats
    
    def process_queue(
        self, 
        sync_fn: Callable[[SyncItem], None],
        batch_size: int = 10
    ) -> Dict[str, int]:
        """Process pending items in the queue.
        
        Args:
            sync_fn: Function that performs the sync (raises exception on failure)
            batch_size: Number of items to process
            
        Returns:
            Dict with counts of processed items
        """
        results = {
            "success": 0,
            "failed": 0,
            "skipped": 0
        }
        
        items = self.get_pending_items(limit=batch_size)
        
        for item in items:
            try:
                # Call sync function
                sync_fn(item)
                
                # Mark as complete
                self.complete_item(item.id)
                results["success"] += 1
                
            except Exception as e:
                # Mark attempt with error
                self.mark_attempt(item.id, str(e))
                results["failed"] += 1
        
        results["skipped"] = len(self.get_pending_items())
        return results
```

### 3. Create tests/implementation/test_step_2_2.py
```python
"""Test sync queue functionality."""
import tempfile
import time
import pytest
from pathlib import Path
from datetime import datetime, timedelta

from src.dr_exp.sync.queue import SyncQueue, SyncItem


def test_sync_queue_basic():
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
            created_at=datetime.utcnow().isoformat()
        )
        
        queue_file = queue.add_item(item)
        assert Path(queue_file).exists()
        
        # Item should have checksum and size
        with open(queue_file, "r") as f:
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
        


def test_sync_queue_processing():
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
                created_at=datetime.utcnow().isoformat()
            )
            queue.add_item(item)
            time.sleep(0.001)  # Ensure different timestamps
        
        # Define sync function
        processed = []
        def mock_sync(item: SyncItem):
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
        with open(queue.history_file, "r") as f:
            lines = f.readlines()
            assert len(lines) == 3
        


def test_sync_queue_retry():
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
            created_at=datetime.utcnow().isoformat()
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
            with open(queue_file, "r") as f:
                data = json.load(f)
                assert data["attempts"] == 1
                assert data["error"] == "Network error"
                assert data["status"] == "pending"  # Still pending
        
        # Simulate time passing (bypass backoff for testing)
        queue.update_item("retry_test", {
            "last_attempt": (datetime.utcnow() - timedelta(minutes=5)).isoformat()
        })
        
        # Now available again
        items = queue.get_pending_items()
        assert len(items) == 1
        
        # Fail until max retries
        for i in range(2):  # 2 more attempts to reach max
            queue.mark_attempt("retry_test", f"Error {i+2}")
            queue.update_item("retry_test", {
                "last_attempt": (datetime.utcnow() - timedelta(minutes=5)).isoformat()
            })
        
        # Should be marked as failed now
        items = queue.get_pending_items()
        assert len(items) == 0
        
        # Check final status
        for queue_file in queue_dir.glob("*_retry_test.json"):
            with open(queue_file, "r") as f:
                data = json.load(f)
                assert data["attempts"] == 3
                assert data["status"] == "failed"
        


def test_sync_queue_complete():
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
            created_at=datetime.utcnow().isoformat()
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
        with open(queue.history_file, "r") as f:
            line = f.readline()
            data = json.loads(line)
            assert data["id"] == "complete_test"
            assert data["status"] == "completed"
            assert data["completed_at"] is not None
        
        # Queue file should be removed
        queue_files = list(queue_dir.glob("*_complete_test.json"))
        assert len(queue_files) == 0
        


def test_sync_queue_ordering():
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
                created_at=datetime.utcnow().isoformat()
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
        


def test_sync_queue_error_handling():
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
                created_at=datetime.utcnow().isoformat()
            )
            queue.add_item(item)
        
        # Sync function that fails for specific items
        def failing_sync(item: SyncItem):
            if "error_1" in item.id:
                raise ValueError("Simulated sync error")
            # Others succeed
        
        # Process queue
        results = queue.process_queue(failing_sync, batch_size=10)
        
        assert results["success"] == 2
        assert results["failed"] == 1
        
        # Check failed item
        for queue_file in queue_dir.glob("*_error_1.json"):
            with open(queue_file, "r") as f:
                data = json.load(f)
                assert data["attempts"] == 1
                assert "Simulated sync error" in data["error"]
                assert data["status"] == "pending"  # Can be retried
        


```

## Validation
```bash
# Run the test with pytest
pt tests/implementation/test_step_2_2.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_2_2.py::test_sync_queue_basic PASSED
# tests/implementation/test_step_2_2.py::test_sync_queue_processing PASSED
# tests/implementation/test_step_2_2.py::test_sync_queue_retry PASSED
# tests/implementation/test_step_2_2.py::test_sync_queue_complete PASSED
# tests/implementation/test_step_2_2.py::test_sync_queue_ordering PASSED
# tests/implementation/test_step_2_2.py::test_sync_queue_error_handling PASSED
# ============================== 6 passed in X.XXs ===============================

# Verify previous tests still work
pt tests/implementation/test_step_2_1.py -v

# Verify code quality (runs ruff linting/formatting + mypy type checks)
ckdr

# Expected: All checks passed!
```

## Common Mistakes
- DO NOT: Use a database for the queue - files are simpler and sufficient
- DO NOT: Implement complex state machines - keep status simple
- DO NOT: Add transaction support - single file operations are atomic
- DO NOT: Forget exponential backoff - prevents hammering failed endpoints
- DO NOT: Keep completed items in queue directory - move to history

## Next Step
Proceed to Step 2.3: Worker Threading Integration