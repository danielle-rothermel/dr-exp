"""Supabase client for remote storage and database operations."""

import os
import hashlib
import time
from pathlib import Path
from typing import Any
import mimetypes
from datetime import datetime, UTC

from supabase import create_client, Client


class SupabaseClient:
    """Client for interacting with Supabase storage and database."""

    def __init__(self, url: str | None = None, key: str | None = None) -> None:
        """Initialize Supabase client with retry logic.

        Args:
            url: Supabase project URL (defaults to SUPABASE_URL env var)
            key: Supabase service role key (defaults to SUPABASE_KEY env var)
        """
        self.url = url or os.environ.get("SUPABASE_URL")
        self.key = key or os.environ.get("SUPABASE_KEY")

        if not self.url or not self.key:
            raise ValueError(
                "Supabase URL and key must be provided or set in environment"
            )

        # Create client with retry logic
        MAX_ATTEMPTS = 3
        for attempt in range(MAX_ATTEMPTS):
            try:
                self.client: Client = create_client(self.url, self.key)
                # Test the connection
                self.client.storage.list_buckets()
                break
            except Exception as e:
                if attempt == MAX_ATTEMPTS - 1:
                    raise Exception(
                        f"Failed to connect to Supabase after 3 attempts: {e}"
                    ) from e
                print(f"Connection attempt {attempt + 1} failed, retrying...")
                time.sleep(1)

        self.bucket_name = "experiments"

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

    def _get_storage_path(
        self, experiment_name: str, job_id: str, file_name: str
    ) -> str:
        """Generate storage path for a file.

        Args:
            experiment_name: Name of experiment
            job_id: Job ID
            file_name: Original filename

        Returns:
            Storage path in bucket
        """
        return f"{experiment_name}/jobs/{job_id}/{file_name}"

    def upload_file(
        self,
        file_path: Path,
        experiment_name: str,
        job_id: str,
        file_type: str,
        metadata: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> tuple[str, str]:
        """Upload a file to Supabase storage.

        Storage Limits:
            - Maximum file size: 5GB for direct upload
            - For files > 100MB, consider using multipart uploads
            - For files > 5GB, use resumable uploads or external storage

        Args:
            file_path: Local file path
            experiment_name: Experiment name
            job_id: Job ID that created this file
            file_type: Type of file (metrics, model, etc.)
            metadata: Optional metadata

        Returns:
            Tuple of (storage_url, checksum)

        Raises:
            Exception: If upload fails
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Check file size
        file_size = file_path.stat().st_size
        if file_size > 5 * 1024 * 1024 * 1024:  # 5GB
            raise ValueError(
                f"File too large ({file_size / 1024 / 1024 / 1024:.1f}GB). "
                "Maximum size is 5GB for direct upload."
            )

        if file_size > 100 * 1024 * 1024:  # 100MB
            print(
                f"Warning: Large file ({file_size / 1024 / 1024:.1f}MB). "
                "Consider using multipart upload for better reliability."
            )

        # Calculate checksum
        checksum = self._calculate_checksum(file_path)

        # Determine MIME type - use safe defaults based on file type
        mime_map = {
            "metrics": "application/json",
            "model": "application/octet-stream",
            "logs": "text/plain",
            "config": "application/json",
            "error": "text/plain",
        }

        # Always use our safe mapping if available
        if file_type in mime_map:
            mime_type = mime_map[file_type]
        else:
            # Only guess for types we don't have mapped
            guessed_type, _ = mimetypes.guess_type(file_path)
            if (
                guessed_type is None or guessed_type.startswith(("chemical/", "model/"))
            ):
                mime_type = "application/octet-stream"
            else:
                mime_type = guessed_type

        # Generate storage path
        storage_path = self._get_storage_path(experiment_name, job_id, file_path.name)

        # Read file content
        with file_path.open("rb") as f:
            file_content = f.read()

        # Upload to storage
        try:
            self.client.storage.from_(self.bucket_name).upload(
                path=storage_path,
                file=file_content,
                file_options={
                    "content-type": mime_type,
                    "x-upsert": "true",  # Overwrite if exists
                },
            )

            # Generate public URL (requires auth to access)
            storage_url = (
                f"{self.url}/storage/v1/object/authenticated/"
                f"{self.bucket_name}/{storage_path}"
            )

            return storage_url, checksum

        except Exception as e:
            # Handle specific Supabase errors
            error_msg = str(e)
            if "already exists" in error_msg:
                # File already uploaded, return URL
                storage_url = (
                    f"{self.url}/storage/v1/object/authenticated/"
                    f"{self.bucket_name}/{storage_path}"
                )
                return storage_url, checksum
            else:
                raise Exception(f"Failed to upload {file_path}: {error_msg}") from e

    def download_file(self, storage_path: str, local_path: Path) -> Path:
        """Download a file from Supabase storage.

        Args:
            storage_path: Path in storage bucket
            local_path: Local path to save file

        Returns:
            Path to downloaded file

        Raises:
            Exception: If download fails
        """
        # Ensure parent directory exists
        local_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Download from storage
            response = self.client.storage.from_(self.bucket_name).download(
                storage_path
            )

            # Write to local file
            with local_path.open("wb") as f:
                f.write(response)

            return local_path

        except Exception as e:
            raise Exception(f"Failed to download {storage_path}: {e!s}") from e

    def list_files(self, prefix: str, limit: int = 100) -> list[dict[str, Any]]:
        """List files in storage with a given prefix.

        Args:
            prefix: Path prefix to filter by
            limit: Maximum number of files to return

        Returns:
            List of file metadata dictionaries
        """
        try:
            response = self.client.storage.from_(self.bucket_name).list(
                path=prefix,
                options={
                    "limit": limit,
                    "sortBy": {"column": "created_at", "order": "desc"},
                },
            )

            return response  # type: ignore

        except Exception as e:
            raise Exception(f"Failed to list files with prefix {prefix}: {e!s}") from e

    def delete_file(self, storage_path: str) -> bool:
        """Delete a file from storage.

        Args:
            storage_path: Path in storage bucket

        Returns:
            True if deleted successfully
        """
        try:
            self.client.storage.from_(self.bucket_name).remove([storage_path])
            return True
        except Exception:
            return False

    def get_signed_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Get a signed URL for temporary access to a file.

        Args:
            storage_path: Path in storage bucket
            expires_in: Seconds until URL expires

        Returns:
            Signed URL
        """
        try:
            response = self.client.storage.from_(self.bucket_name).create_signed_url(
                path=storage_path, expires_in=expires_in
            )

            return response["signedURL"]  # type: ignore

        except Exception as e:
            raise Exception(f"Failed to create signed URL: {e!s}") from e

    def get_or_create_experiment(
        self,
        experiment_name: str,
        base_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Get or create an experiment in the database.

        Args:
            experiment_name: Name of the experiment
            base_path: Base path for the experiment
            metadata: Optional metadata

        Returns:
            Experiment ID (UUID string)
        """
        try:
            # Try to get existing experiment
            response = (
                self.client.table("experiments")
                .select("id")
                .eq("experiment_name", experiment_name)
                .eq("base_path", base_path)
                .execute()
            )

            if response.data and len(response.data) > 0:
                return str(response.data[0]["id"])

            # Create new experiment
            data = {
                "experiment_name": experiment_name,
                "base_path": base_path,
                "metadata": metadata or {},
            }

            response = self.client.table("experiments").insert(data).execute()

            if response.data and len(response.data) > 0:
                return str(response.data[0]["id"])
            else:
                raise Exception("Failed to create experiment")

        except Exception as e:
            raise Exception(f"Failed to get/create experiment: {e!s}") from e

    def sync_job(self, job_data: dict[str, Any], experiment_id: str) -> bool:
        """Sync a job to the database.

        Args:
            job_data: Job data from local JobDB
            experiment_id: Experiment ID

        Returns:
            True if synced successfully
        """
        try:
            # Prepare job data for database
            db_job = {
                "id": job_data["id"],
                "experiment_id": experiment_id,
                "config": job_data["config"],
                "priority": job_data.get("priority", 100),
                "status": job_data["status"],
                "worker_id": job_data.get("worker_id"),
                "created_at": job_data.get("created_at"),
                "updated_at": job_data.get("updated_at"),
                "started_at": job_data.get("started_at"),
                "completed_at": job_data.get("completed_at"),
                "last_heartbeat": job_data.get("last_heartbeat"),
                "attempts": job_data.get("attempts", 0),
                "error": job_data.get("error"),
                "final_metrics": job_data.get("final_metrics"),
                "reserved_for": job_data.get("reserved_for"),
                "reservation_time": job_data.get("reservation_time"),
                "priority_boosted": job_data.get("priority_boosted", False),
                "recovery_count": job_data.get("recovery_count", 0),
                "last_recovery": job_data.get("last_recovery"),
            }

            # Remove None values
            db_job = {k: v for k, v in db_job.items() if v is not None}

            # Upsert job (insert or update)
            response = (
                self.client.table("jobs").upsert(db_job, on_conflict="id").execute()
            )

            return response.data is not None

        except Exception as e:
            raise Exception(f"Failed to sync job {job_data.get('id')}: {e!s}") from e

    def create_sync_status(
        self,
        job_id: str,
        file_path: str,
        file_type: str,
        checksum: str,
        size_bytes: int,
        storage_url: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a sync status record.

        Args:
            job_id: Job that created the file
            file_path: Original file path
            file_type: Type of file
            checksum: File checksum
            size_bytes: File size
            storage_url: URL in storage
            metadata: Optional metadata

        Returns:
            Sync status ID
        """
        try:
            data = {
                "job_id": job_id,
                "file_path": file_path,
                "file_type": file_type,
                "checksum": checksum,
                "size_bytes": size_bytes,
                "storage_url": storage_url,
                "status": "completed",
                "completed_at": datetime.now(UTC).isoformat(),
                "metadata": metadata or {},
            }

            response = self.client.table("sync_status").insert(data).execute()

            if response.data and len(response.data) > 0:
                return str(response.data[0]["id"])
            else:
                raise Exception("Failed to create sync status")

        except Exception as e:
            raise Exception(f"Failed to create sync status: {e!s}") from e

    def update_sync_status(
        self, sync_id: str, status: str, error: str | None = None
    ) -> bool:
        """Update sync status for a file.

        Args:
            sync_id: Sync status ID
            status: New status
            error: Optional error message

        Returns:
            True if updated successfully
        """
        try:
            data = {"status": status, "updated_at": datetime.now(UTC).isoformat()}

            if error:
                data["error"] = error
                data["last_attempt"] = datetime.now(UTC).isoformat()

            if status == "completed":
                data["completed_at"] = datetime.now(UTC).isoformat()

            response = (
                self.client.table("sync_status")
                .update(data)
                .eq("id", sync_id)
                .execute()
            )

            return response.data is not None

        except Exception as e:
            raise Exception(f"Failed to update sync status: {e!s}") from e

    def get_experiment_jobs(
        self, experiment_id: str, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get jobs for an experiment.

        Args:
            experiment_id: Experiment ID
            status: Optional status filter
            limit: Maximum number of jobs

        Returns:
            List of job records
        """
        try:
            query = (
                self.client.table("jobs")
                .select("*")
                .eq("experiment_id", experiment_id)
                .order("created_at", desc=True)
                .limit(limit)
            )

            if status:
                query = query.eq("status", status)

            response = query.execute()

            return response.data or []

        except Exception as e:
            raise Exception(f"Failed to get experiment jobs: {e!s}") from e

    def get_experiment_stats(self, experiment_id: str) -> dict[str, Any]:
        """Get statistics for an experiment.

        Args:
            experiment_id: Experiment ID

        Returns:
            Dictionary with experiment statistics
        """
        try:
            # Use the experiment_stats view
            response = (
                self.client.table("experiment_stats")
                .select("*")
                .eq("id", experiment_id)
                .execute()
            )

            if response.data and len(response.data) > 0:
                return dict(response.data[0])

            # Fallback to manual calculation
            jobs = self.get_experiment_jobs(experiment_id, limit=1000)

            stats = {
                "total_jobs": len(jobs),
                "queued_jobs": len([j for j in jobs if j["status"] == "queued"]),
                "running_jobs": len([j for j in jobs if j["status"] == "running"]),
                "completed_jobs": len([j for j in jobs if j["status"] == "completed"]),
                "failed_jobs": len([j for j in jobs if j["status"] == "failed"]),
                "killed_jobs": len([j for j in jobs if j["status"] == "killed"]),
            }

            return stats

        except Exception as e:
            raise Exception(f"Failed to get experiment stats: {e!s}") from e

    def get_job_sync_status(self, job_id: str) -> list[dict[str, Any]]:
        """Get sync status for all files from a job.

        Args:
            job_id: Job ID

        Returns:
            List of sync status records
        """
        try:
            response = (
                self.client.table("sync_status")
                .select("*")
                .eq("job_id", job_id)
                .order("created_at", desc=True)
                .execute()
            )

            return response.data or []

        except Exception as e:
            raise Exception(f"Failed to get job sync status: {e!s}") from e

    def batch_sync_jobs(
        self, jobs: list[dict[str, Any]], experiment_id: str
    ) -> dict[str, int]:
        """Sync multiple jobs in batch.

        Args:
            jobs: List of job data dictionaries
            experiment_id: Experiment ID

        Returns:
            Dictionary with success/failed counts
        """
        results = {"success": 0, "failed": 0}

        for job_data in jobs:
            try:
                if self.sync_job(job_data, experiment_id):
                    results["success"] += 1
                else:
                    results["failed"] += 1
            except Exception:
                results["failed"] += 1

        return results

    def test_connection(self) -> bool:
        """Test connection to Supabase.

        Returns:
            True if connection successful
        """
        try:
            # Try to list buckets
            response = self.client.storage.list_buckets()

            # Check our bucket exists
            bucket_names = [b.name for b in response]
            return self.bucket_name in bucket_names

        except Exception:
            return False
