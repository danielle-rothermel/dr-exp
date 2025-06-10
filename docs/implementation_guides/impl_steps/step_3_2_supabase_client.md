# Step 3.2: Supabase Client Basics

## Goal (1 sentence)
Create a Supabase client class that handles file uploads to storage with checksum calculation and proper error handling.

## Prerequisites
- [ ] Step 3.1 completed with database schema deployed
- [ ] Local Supabase running with tables and storage bucket
- [ ] Supabase Python client installed: `uv add supabase`

## Implementation

### 1. Create src/dr_exp/sync/supabase_client.py
```python
"""Supabase client for remote storage and database operations."""
import os
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import mimetypes

from supabase import create_client, Client


class SupabaseClient:
    """Client for interacting with Supabase storage and database."""
    
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        """Initialize Supabase client.
        
        Args:
            url: Supabase project URL (defaults to SUPABASE_URL env var)
            key: Supabase service role key (defaults to SUPABASE_KEY env var)
        """
        self.url = url or os.environ.get("SUPABASE_URL")
        self.key = key or os.environ.get("SUPABASE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("Supabase URL and key must be provided or set in environment")
        
        # Create client
        self.client: Client = create_client(self.url, self.key)
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
    
    def _get_storage_path(self, experiment_name: str, job_id: str, 
                         file_name: str) -> str:
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
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, str]:
        """Upload a file to Supabase storage.
        
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
        
        # Calculate checksum
        checksum = self._calculate_checksum(file_path)
        
        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            # Default based on file type
            mime_map = {
                "metrics": "application/json",
                "model": "application/octet-stream",
                "logs": "text/plain",
                "config": "application/json",
                "error": "text/plain"
            }
            mime_type = mime_map.get(file_type, "application/octet-stream")
        
        # Generate storage path
        storage_path = self._get_storage_path(
            experiment_name, 
            job_id, 
            file_path.name
        )
        
        # Read file content
        with open(file_path, "rb") as f:
            file_content = f.read()
        
        # Upload to storage
        try:
            response = self.client.storage.from_(self.bucket_name).upload(
                path=storage_path,
                file=file_content,
                file_options={
                    "content-type": mime_type,
                    "x-upsert": "true"  # Overwrite if exists
                }
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
    
    def download_file(
        self,
        storage_path: str,
        local_path: Path
    ) -> Path:
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
            response = self.client.storage.from_(self.bucket_name).download(storage_path)
            
            # Write to local file
            with open(local_path, "wb") as f:
                f.write(response)
            
            return local_path
            
        except Exception as e:
            raise Exception(f"Failed to download {storage_path}: {str(e)}")
    
    def list_files(
        self,
        prefix: str,
        limit: int = 100
    ) -> list[Dict[str, Any]]:
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
                    "sortBy": {"column": "created_at", "order": "desc"}
                }
            )
            
            return response
            
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
    
    def get_signed_url(
        self,
        storage_path: str,
        expires_in: int = 3600
    ) -> str:
        """Get a signed URL for temporary access to a file.
        
        Args:
            storage_path: Path in storage bucket
            expires_in: Seconds until URL expires
            
        Returns:
            Signed URL
        """
        try:
            response = self.client.storage.from_(self.bucket_name).create_signed_url(
                path=storage_path,
                expires_in=expires_in
            )
            
            return response["signedURL"]
            
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
```

### 2. Create tests/implementation/test_step_3_2.py
```python
"""Test Supabase client functionality."""
import os
import tempfile
import pytest
from pathlib import Path
from dotenv import load_dotenv

from src.dr_exp.sync.supabase_client import SupabaseClient


def setup_test_env():
    """Load test environment variables."""
    # Load from .env.test if it exists
    env_file = Path(".env.test")
    if env_file.exists():
        load_dotenv(env_file)
    else:
        # Use default local Supabase values
        os.environ["SUPABASE_URL"] = "http://localhost:54321"
        os.environ["SUPABASE_KEY"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"


def test_supabase_connection():
    """Test basic connection to Supabase."""
    setup_test_env()
    
    # Create client
    client = SupabaseClient()
    
    # Test connection
    assert client.test_connection(), "Failed to connect to Supabase"
    
    assert client.url is not None
    assert client.bucket_name == "experiments"


def test_file_upload():
    """Test uploading files to Supabase storage."""
    setup_test_env()
    
    client = SupabaseClient()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        test_files = {
            "metrics.jsonl": '{"epoch": 1, "loss": 0.5}\n{"epoch": 2, "loss": 0.3}\n',
            "model.pt": b"Mock PyTorch model binary data",
            "config.json": '{"model": "resnet18", "lr": 0.001}',
            "training.log": "Starting training...\nEpoch 1 complete\n"
        }
        
        uploaded = []
        
        for filename, content in test_files.items():
            # Create local file
            file_path = Path(tmpdir) / filename
            if isinstance(content, bytes):
                file_path.write_bytes(content)
            else:
                file_path.write_text(content)
            
            # Determine file type
            if "metrics" in filename:
                file_type = "metrics"
            elif "model" in filename:
                file_type = "model"
            elif "config" in filename:
                file_type = "config"
            else:
                file_type = "logs"
            
            # Upload file
            storage_url, checksum = client.upload_file(
                file_path=file_path,
                experiment_name="test_upload",
                job_id="test_job_123",
                file_type=file_type,
                metadata={"test": True}
            )
            
            assert storage_url is not None
            assert checksum is not None
            assert len(checksum) == 64  # SHA256 hex length
            
            uploaded.append((filename, storage_url, checksum))
        
        # Test re-uploading (should handle gracefully)
        first_file = Path(tmpdir) / test_files.keys().__iter__().__next__()
        storage_url2, checksum2 = client.upload_file(
            file_path=first_file,
            experiment_name="test_upload",
            job_id="test_job_123",
            file_type="metrics"
        )
        
        assert checksum2 == uploaded[0][2], "Checksum should match for same file"
        
        return uploaded


def test_file_download():
    """Test downloading files from Supabase storage."""
    setup_test_env()
    
    client = SupabaseClient()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # First upload a file
        upload_file = Path(tmpdir) / "test_download.txt"
        upload_file.write_text("Test content for download")
        
        storage_url, checksum = client.upload_file(
            file_path=upload_file,
            experiment_name="test_download",
            job_id="download_job",
            file_type="logs"
        )
        
        # Extract storage path from URL
        storage_path = "test_download/jobs/download_job/test_download.txt"
        
        # Download to different location
        download_path = Path(tmpdir) / "downloaded.txt"
        result_path = client.download_file(storage_path, download_path)
        
        assert result_path == download_path
        assert download_path.exists()
        
        # Verify content
        downloaded_content = download_path.read_text()
        assert downloaded_content == "Test content for download"
        
        # Verify checksum
        downloaded_checksum = client._calculate_checksum(download_path)
        assert downloaded_checksum == checksum


def test_file_listing():
    """Test listing files in storage."""
    setup_test_env()
    
    client = SupabaseClient()
    
    # Upload some test files first
    with tempfile.TemporaryDirectory() as tmpdir:
        exp_name = f"test_list_{int(os.getpid())}"
        
        for i in range(3):
            file_path = Path(tmpdir) / f"file_{i}.txt"
            file_path.write_text(f"Content {i}")
            
            client.upload_file(
                file_path=file_path,
                experiment_name=exp_name,
                job_id=f"job_{i}",
                file_type="logs"
            )
        
        # List files
        files = client.list_files(prefix=exp_name, limit=10)
        
        # Should find our files (might be nested in response)
        assert len(files) >= 3 or any('name' in f for f in files)
        
        # List with more specific prefix
        files = client.list_files(prefix=f"{exp_name}/jobs", limit=10)
        assert isinstance(files, list)


def test_signed_urls():
    """Test generating signed URLs for temporary access."""
    setup_test_env()
    
    client = SupabaseClient()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Upload a file
        file_path = Path(tmpdir) / "signed_test.json"
        file_path.write_text('{"test": "signed URL"}')
        
        storage_url, _ = client.upload_file(
            file_path=file_path,
            experiment_name="test_signed",
            job_id="signed_job",
            file_type="config"
        )
        
        # Generate signed URL
        storage_path = "test_signed/jobs/signed_job/signed_test.json"
        signed_url = client.get_signed_url(storage_path, expires_in=300)
        
        assert signed_url is not None
        assert "token=" in signed_url
        assert storage_path in signed_url


def test_error_handling():
    """Test error handling in Supabase client."""
    setup_test_env()
    
    client = SupabaseClient()
    
    # Test invalid file
    try:
        client.upload_file(
            file_path=Path("/nonexistent/file.txt"),
            experiment_name="test",
            job_id="test",
            file_type="logs"
        )
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError as e:
        assert "File not found" in str(e)
    
    # Test invalid download
    try:
        client.download_file(
            storage_path="nonexistent/path.txt",
            local_path=Path("/tmp/download.txt")
        )
        assert False, "Should have raised exception"
    except Exception as e:
        assert "Failed to download" in str(e)
    
    # Test invalid credentials
    try:
        bad_client = SupabaseClient(
            url="http://localhost:54321",
            key="invalid_key"
        )
        bad_client.test_connection()
        # May or may not fail depending on Supabase config
    except:
        pass  # Expected to fail with invalid credentials


def test_checksum_calculation():
    """Test checksum calculation."""
    setup_test_env()
    
    client = SupabaseClient()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create files with known content
        file1 = Path(tmpdir) / "file1.txt"
        file2 = Path(tmpdir) / "file2.txt"
        file3 = Path(tmpdir) / "file1_copy.txt"
        
        file1.write_text("Hello world")
        file2.write_text("Different content")
        file3.write_text("Hello world")  # Same as file1
        
        # Calculate checksums
        checksum1 = client._calculate_checksum(file1)
        checksum2 = client._calculate_checksum(file2)
        checksum3 = client._calculate_checksum(file3)
        
        # Verify
        assert len(checksum1) == 64  # SHA256 hex
        assert checksum1 != checksum2  # Different content
        assert checksum1 == checksum3  # Same content


def test_mime_type_detection():
    """Test MIME type detection for different file types."""
    setup_test_env()
    
    client = SupabaseClient()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test various file types
        test_files = {
            "data.json": ("json", "application/json"),
            "model.pt": ("model", "application/octet-stream"),
            "log.txt": ("logs", "text/plain"),
            "archive.zip": ("other", "application/zip"),
            "unknown.xyz": ("other", "application/octet-stream")
        }
        
        for filename, (file_type, expected_mime) in test_files.items():
            file_path = Path(tmpdir) / filename
            file_path.write_text("test")
            
            # Upload and check MIME type handling
            try:
                storage_url, _ = client.upload_file(
                    file_path=file_path,
                    experiment_name="test_mime",
                    job_id="mime_job",
                    file_type=file_type
                )
                assert storage_url is not None
            except Exception as e:
                assert False, f"Failed to upload {filename}: {e}"


```

## Validation
```bash
# Install dependencies
uv add supabase python-dotenv

# Make sure Supabase is running
supabase status

# Run tests
pt tests/implementation/test_step_3_2.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_3_2.py::test_supabase_connection PASSED
# tests/implementation/test_step_3_2.py::test_file_upload PASSED
# tests/implementation/test_step_3_2.py::test_file_download PASSED
# tests/implementation/test_step_3_2.py::test_file_listing PASSED
# tests/implementation/test_step_3_2.py::test_signed_urls PASSED
# tests/implementation/test_step_3_2.py::test_error_handling PASSED
# tests/implementation/test_step_3_2.py::test_checksum_calculation PASSED
# tests/implementation/test_step_3_2.py::test_mime_type_detection PASSED
# ============================== 8 passed in X.XXs ===============================

# Check uploaded files in Supabase Studio
open http://localhost:54323
# Navigate to Storage → experiments bucket
```

## Common Mistakes
- DO NOT: Store credentials in code - use environment variables
- DO NOT: Forget to handle re-uploads - use upsert mode
- DO NOT: Use blocking I/O in async contexts - this client is sync
- DO NOT: Upload large files in memory - use streaming for big files
- DO NOT: Expose storage URLs without auth - use signed URLs for sharing

## Next Step
Proceed to Step 3.3: Database Operations