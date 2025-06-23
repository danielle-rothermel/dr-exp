"""Sync queue for managing file uploads."""

import json
import time
import hashlib
from pathlib import Path
from typing import Any
from collections.abc import Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict


@dataclass
class SyncItem:
    """Represents an item to be synced."""

    id: str
    job_id: str
    file_path: str
    file_type: str
    metadata: dict[str, Any]
    created_at: str
    status: str = "pending"
    attempts: int = 0
    last_attempt: str | None = None
    error: str | None = None
    completed_at: str | None = None
    checksum: str | None = None
    size_bytes: int | None = None


class SyncQueue:
    """Manages queue of files to sync."""

    def __init__(self, queue_dir: Path, max_retries: int = 3) -> None:
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
        with file_path.open("rb") as f:
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

        with queue_file.open("w") as f:
            json.dump(asdict(sync_item), f, indent=2)

        return str(queue_file)

    def get_pending_items(self, limit: int | None = None) -> list[SyncItem]:
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
                with queue_file.open() as f:
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

    def update_item(self, item_id: str, updates: dict[str, Any]) -> bool:
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
                with queue_file.open() as f:
                    data = json.load(f)

                # Apply updates
                data.update(updates)

                # Write back
                with queue_file.open("w") as f:
                    json.dump(data, f, indent=2)

                return True

            except (OSError, json.JSONDecodeError):
                continue

        return False

    def mark_attempt(self, item_id: str, error: str | None = None) -> bool:
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
            current_attempts = 0

            # Get current attempts to increment
            for queue_file in self.queue_dir.glob(f"*_{item_id}.json"):
                try:
                    with queue_file.open() as f:
                        data = json.load(f)
                        current_attempts = data.get("attempts", 0) + 1
                    break
                except (OSError, json.JSONDecodeError):
                    continue

            updates = {
                "attempts": current_attempts,
                "last_attempt": now,
                "error": error,
            }

            # Mark as failed if too many attempts
            if current_attempts >= self.max_retries:
                updates["status"] = "failed"
        else:
            # Successful attempt
            updates = {"status": "completed", "completed_at": now, "error": None}

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
                with queue_file.open() as f:
                    data = json.load(f)

                # Update status
                data["status"] = "completed"
                data["completed_at"] = datetime.utcnow().isoformat()
                data["error"] = None

                # Append to history
                with self.history_file.open("a") as f:
                    f.write(json.dumps(data) + "\n")

                # Remove from queue
                queue_file.unlink()

                return True

            except (OSError, json.JSONDecodeError):
                continue

        return False

    def get_stats(self) -> dict[str, int]:
        """Get queue statistics.

        Returns:
            Dict with counts by status
        """
        stats = {"pending": 0, "failed": 0, "completed": 0, "total": 0}

        # Count queue files
        for queue_file in self.queue_dir.glob("*.json"):
            if queue_file.name.startswith("_"):
                continue

            try:
                with queue_file.open() as f:
                    data = json.load(f)
                    status = data.get("status", "pending")
                    if status in stats:
                        stats[status] += 1
                    stats["total"] += 1
            except (OSError, json.JSONDecodeError):
                continue

        # Count history entries
        if self.history_file.exists():
            with self.history_file.open() as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        if data.get("status") == "completed":
                            stats["completed"] += 1
                            stats["total"] += 1
                    except (OSError, json.JSONDecodeError):
                        continue

        return stats

    def process_queue(
        self, sync_fn: Callable[[SyncItem], None], batch_size: int = 10
    ) -> dict[str, int]:
        """Process pending items in the queue.

        Args:
            sync_fn: Function that performs the sync (raises exception on failure)
            batch_size: Number of items to process

        Returns:
            Dict with counts of processed items
        """
        results = {"success": 0, "failed": 0, "skipped": 0}

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
