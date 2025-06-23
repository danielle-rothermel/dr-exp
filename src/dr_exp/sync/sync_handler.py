"""Sync handler that connects sync queue to Supabase."""

from pathlib import Path
from typing import Optional, Dict, Any

from .queue import SyncItem
from .supabase_client import SupabaseClient


class SyncHandler:
    """Handles syncing files from queue to Supabase."""

    def __init__(
        self,
        experiment_name: str,
        base_path: str,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ):
        """Initialize sync handler.

        Args:
            experiment_name: Name of the experiment
            base_path: Base path for the experiment
            supabase_url: Supabase URL (optional, uses env var)
            supabase_key: Supabase key (optional, uses env var)
        """
        self.experiment_name = experiment_name
        self.base_path = base_path

        # Initialize Supabase client
        try:
            self.client: Optional[SupabaseClient] = SupabaseClient(
                url=supabase_url, key=supabase_key
            )
            self.enabled = True

            # Get or create experiment
            self.experiment_id: Optional[str] = self.client.get_or_create_experiment(
                experiment_name=experiment_name, base_path=base_path
            )
        except Exception as e:
            print(f"[SyncHandler] Failed to initialize Supabase: {e}")
            print("[SyncHandler] Sync disabled - files will remain in queue")
            self.client = None
            self.enabled = False
            self.experiment_id = None

    def sync_file(self, item: SyncItem) -> Dict[str, Any]:
        """Sync a single file to Supabase.

        Args:
            item: Sync item to process

        Returns:
            Dict with sync result including bytes_uploaded

        Raises:
            Exception: If sync fails (for retry logic)
        """
        if not self.enabled or not self.client:
            raise Exception("Sync is disabled")

        file_path = Path(item.file_path)

        # Check file exists
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = file_path.stat().st_size

        # Upload file
        storage_url, checksum = self.client.upload_file(
            file_path=file_path,
            experiment_name=self.experiment_name,
            job_id=item.job_id,
            file_type=item.file_type,
            metadata=item.metadata,
        )

        # Create sync status record
        self.client.create_sync_status(
            job_id=item.job_id,
            file_path=item.file_path,
            file_type=item.file_type,
            checksum=checksum,
            size_bytes=item.size_bytes or file_size,
            storage_url=storage_url,
            metadata=item.metadata,
        )

        print(f"[SyncHandler] Uploaded {file_path.name} ({item.file_type})")

        # Return metrics
        return {"bytes_uploaded": file_size, "file_type": item.file_type}

    def sync_job_data(self, job_data: Dict[str, Any]) -> bool:
        """Sync job metadata to Supabase.

        Args:
            job_data: Job data dictionary

        Returns:
            True if synced successfully
        """
        if not self.enabled or not self.client or not self.experiment_id:
            return False

        try:
            return self.client.sync_job(job_data, self.experiment_id)
        except Exception as e:
            print(f"[SyncHandler] Failed to sync job {job_data.get('id')}: {e}")
            return False

    def is_available(self) -> bool:
        """Check if sync is available.

        Returns:
            True if Supabase connection is working
        """
        if not self.enabled or not self.client:
            return False

        try:
            return self.client.test_connection()
        except Exception:
            return False
