"""Supabase client for remote storage and database operations."""

import os
import hashlib
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import mimetypes

from supabase import create_client, Client


class SupabaseClient:
    """Client for interacting with Supabase storage and database."""

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None) -> None:
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
        for attempt in range(3):
            try:
                self.client: Client = create_client(self.url, self.key)
                # Test the connection
                self.client.storage.list_buckets()
                break
            except Exception as e:
                if attempt == 2:
                    raise Exception(
                        f"Failed to connect to Supabase after 3 attempts: {e}"
                    )
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
        with open(file_path, "rb") as f:
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
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
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
                f"File too large ({file_size / 1024 / 1024 / 1024:.1f}GB). Maximum size is 5GB for direct upload."
            )

        if file_size > 100 * 1024 * 1024:  # 100MB
            print(
                f"Warning: Large file ({file_size / 1024 / 1024:.1f}MB). Consider using multipart upload for better reliability."
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
            if guessed_type is None:
                mime_type = "application/octet-stream"
            # Filter out potentially problematic MIME types
            elif guessed_type.startswith("chemical/") or guessed_type.startswith(
                "model/"
            ):
                mime_type = "application/octet-stream"
            else:
                mime_type = guessed_type

        # Generate storage path
        storage_path = self._get_storage_path(experiment_name, job_id, file_path.name)

        # Read file content
        with open(file_path, "rb") as f:
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
            storage_url = f"{self.url}/storage/v1/object/authenticated/{self.bucket_name}/{storage_path}"

            return storage_url, checksum

        except Exception as e:
            # Handle specific Supabase errors
            error_msg = str(e)
            if "already exists" in error_msg:
                # File already uploaded, return URL
                storage_url = f"{self.url}/storage/v1/object/authenticated/{self.bucket_name}/{storage_path}"
                return storage_url, checksum
            else:
                raise Exception(f"Failed to upload {file_path}: {error_msg}")

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
            with open(local_path, "wb") as f:
                f.write(response)

            return local_path

        except Exception as e:
            raise Exception(f"Failed to download {storage_path}: {str(e)}")

    def list_files(self, prefix: str, limit: int = 100) -> list[Dict[str, Any]]:
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
            raise Exception(f"Failed to list files with prefix {prefix}: {str(e)}")

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
            raise Exception(f"Failed to create signed URL: {str(e)}")

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
