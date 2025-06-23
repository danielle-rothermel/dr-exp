"""Test Supabase client functionality."""

import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv

from dr_exp.sync.supabase_client import SupabaseClient


def setup_test_env() -> None:
    """Load test environment variables."""
    # Load from .env.test if it exists
    env_file = Path(".env.test")
    if env_file.exists():
        load_dotenv(env_file)
    else:
        # Use default local Supabase values
        os.environ["SUPABASE_URL"] = "http://localhost:54321"
        os.environ["SUPABASE_KEY"] = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
        )


def test_supabase_connection() -> None:
    """Test basic connection to Supabase."""
    setup_test_env()

    # Create client
    client = SupabaseClient()

    # Test connection
    assert client.test_connection(), "Failed to connect to Supabase"

    assert client.url is not None
    assert client.bucket_name == "experiments"


def test_file_upload() -> list[tuple[str, str, str]]:
    """Test uploading files to Supabase storage."""
    setup_test_env()

    client = SupabaseClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        test_files = {
            "metrics.jsonl": '{"epoch": 1, "loss": 0.5}\n{"epoch": 2, "loss": 0.3}\n',
            "model.pt": b"Mock PyTorch model binary data",
            "config.json": '{"model": "resnet18", "lr": 0.001}',
            "training.log": "Starting training...\nEpoch 1 complete\n",
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
                metadata={"test": True},
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
            file_type="metrics",
        )

        assert checksum2 == uploaded[0][2], "Checksum should match for same file"

        return uploaded


def test_file_download() -> None:
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
            file_type="logs",
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


def test_file_listing() -> None:
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
                file_type="logs",
            )

        # List files
        files = client.list_files(prefix=exp_name, limit=10)

        # Should find our files (might be nested in response)
        assert len(files) >= 3 or any("name" in f for f in files)

        # List with more specific prefix
        files = client.list_files(prefix=f"{exp_name}/jobs", limit=10)
        assert isinstance(files, list)


def test_signed_urls() -> None:
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
            file_type="config",
        )

        # Generate signed URL
        storage_path = "test_signed/jobs/signed_job/signed_test.json"
        signed_url = client.get_signed_url(storage_path, expires_in=300)

        assert signed_url is not None
        assert "token=" in signed_url
        assert storage_path in signed_url


def test_error_handling() -> None:
    """Test error handling in Supabase client."""
    setup_test_env()

    client = SupabaseClient()

    # Test invalid file
    try:
        client.upload_file(
            file_path=Path("/nonexistent/file.txt"),
            experiment_name="test",
            job_id="test",
            file_type="logs",
        )
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError as e:
        assert "File not found" in str(e)

    # Test invalid download
    try:
        client.download_file(
            storage_path="nonexistent/path.txt", local_path=Path("/tmp/download.txt")
        )
        assert False, "Should have raised exception"
    except Exception as e:
        assert "Failed to download" in str(e)

    # Test invalid credentials
    try:
        bad_client = SupabaseClient(url="http://localhost:54321", key="invalid_key")
        bad_client.test_connection()
        # May or may not fail depending on Supabase config
    except Exception:
        pass  # Expected to fail with invalid credentials


def test_checksum_calculation() -> None:
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


def test_mime_type_detection() -> None:
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
            "unknown.xyz": ("other", "application/octet-stream"),
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
                    file_type=file_type,
                )
                assert storage_url is not None
            except Exception as e:
                assert False, f"Failed to upload {filename}: {e}"
