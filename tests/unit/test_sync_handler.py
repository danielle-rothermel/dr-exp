"""Unit tests for SyncHandler functionality."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, UTC

import pytest

from dr_exp.sync.sync_handler import SyncHandler
from dr_exp.sync.queue import SyncItem
from dr_exp.sync.supabase_client import SupabaseClient


class TestSyncHandler:
    """Test cases for SyncHandler."""

    def test_init_success(self) -> None:
        """Test successful initialization with Supabase."""
        with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
            mock_client = Mock(spec=SupabaseClient)
            mock_client.get_or_create_experiment.return_value = "exp_123"
            mock_client_class.return_value = mock_client

            handler = SyncHandler(
                experiment_name="test_exp",
                base_path="/test/path",
                supabase_url="https://test.supabase.co",
                supabase_key="test_key",
            )

            assert handler.experiment_name == "test_exp"
            assert handler.base_path == "/test/path"
            assert handler.enabled is True
            assert handler.client is mock_client
            assert handler.experiment_id == "exp_123"

            mock_client_class.assert_called_once_with(
                url="https://test.supabase.co", key="test_key"
            )
            mock_client.get_or_create_experiment.assert_called_once_with(
                experiment_name="test_exp", base_path="/test/path"
            )

    def test_init_supabase_failure(self) -> None:
        """Test initialization when Supabase fails."""
        with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
            mock_client_class.side_effect = Exception("Connection failed")

            with patch("builtins.print") as mock_print:
                handler = SyncHandler(
                    experiment_name="test_exp", base_path="/test/path"
                )

                assert handler.enabled is False
                assert handler.client is None
                assert handler.experiment_id is None

                mock_print.assert_any_call(
                    "[SyncHandler] Failed to initialize Supabase: Connection failed"
                )
                mock_print.assert_any_call(
                    "[SyncHandler] Sync disabled - files will remain in queue"
                )

    def test_init_experiment_creation_failure(self) -> None:
        """Test initialization when experiment creation fails."""
        with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
            mock_client = Mock(spec=SupabaseClient)
            mock_client.get_or_create_experiment.side_effect = Exception("DB error")
            mock_client_class.return_value = mock_client

            with patch("builtins.print") as mock_print:
                handler = SyncHandler(
                    experiment_name="test_exp", base_path="/test/path"
                )

                assert handler.enabled is False
                assert handler.client is None
                assert handler.experiment_id is None

                mock_print.assert_any_call(
                    "[SyncHandler] Failed to initialize Supabase: DB error"
                )

    def test_sync_file_success(self) -> None:
        """Test successful file sync."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_content = "test content"
            test_file.write_text(test_content)

            # Mock Supabase client
            with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
                mock_client = Mock(spec=SupabaseClient)
                mock_client.get_or_create_experiment.return_value = "exp_123"
                mock_client.upload_file.return_value = (
                    "https://storage.url/file",
                    "checksum123",
                )
                mock_client_class.return_value = mock_client

                handler = SyncHandler("test_exp", "/test/path")

                # Create sync item
                item = SyncItem(
                    id="sync_1",
                    job_id="job_1",
                    file_path=str(test_file),
                    file_type="log",
                    metadata={"key": "value"},
                    created_at=datetime.now(UTC).isoformat(),
                )

                with patch("builtins.print") as mock_print:
                    result = handler.sync_file(item)

                    assert result["bytes_uploaded"] == len(test_content)
                    assert result["file_type"] == "log"

                    # Verify upload_file was called correctly
                    mock_client.upload_file.assert_called_once_with(
                        file_path=test_file,
                        experiment_name="test_exp",
                        job_id="job_1",
                        file_type="log",
                        metadata={"key": "value"},
                    )

                    # Verify sync status was created
                    mock_client.create_sync_status.assert_called_once_with(
                        job_id="job_1",
                        file_path=str(test_file),
                        file_type="log",
                        checksum="checksum123",
                        size_bytes=len(test_content),
                        storage_url="https://storage.url/file",
                        metadata={"key": "value"},
                    )

                    mock_print.assert_called_with(
                        "[SyncHandler] Uploaded test.txt (log)"
                    )

    def test_sync_file_disabled(self) -> None:
        """Test sync_file when sync is disabled."""
        with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
            mock_client_class.side_effect = Exception("No connection")

            handler = SyncHandler("test_exp", "/test/path")

            item = SyncItem(
                id="sync_1",
                job_id="job_1",
                file_path="/nonexistent/file.txt",
                file_type="log",
                metadata={},
                created_at=datetime.now(UTC).isoformat(),
            )

            with pytest.raises(Exception, match="Sync is disabled"):
                handler.sync_file(item)

    def test_sync_file_missing_file(self) -> None:
        """Test sync_file with missing file."""
        with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
            mock_client = Mock(spec=SupabaseClient)
            mock_client.get_or_create_experiment.return_value = "exp_123"
            mock_client_class.return_value = mock_client

            handler = SyncHandler("test_exp", "/test/path")

            item = SyncItem(
                id="sync_1",
                job_id="job_1",
                file_path="/nonexistent/file.txt",
                file_type="log",
                metadata={},
                created_at=datetime.now(UTC).isoformat(),
            )

            with pytest.raises(
                FileNotFoundError, match="File not found: /nonexistent/file.txt"
            ):
                handler.sync_file(item)

    def test_sync_file_upload_failure(self) -> None:
        """Test sync_file when upload fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
                mock_client = Mock(spec=SupabaseClient)
                mock_client.get_or_create_experiment.return_value = "exp_123"
                mock_client.upload_file.side_effect = Exception("Upload failed")
                mock_client_class.return_value = mock_client

                handler = SyncHandler("test_exp", "/test/path")

                item = SyncItem(
                    id="sync_1",
                    job_id="job_1",
                    file_path=str(test_file),
                    file_type="log",
                    metadata={},
                    created_at=datetime.now(UTC).isoformat(),
                )

                with pytest.raises(Exception, match="Upload failed"):
                    handler.sync_file(item)

                # Should not call create_sync_status if upload fails
                mock_client.create_sync_status.assert_not_called()

    def test_sync_file_with_item_size_bytes(self) -> None:
        """Test sync_file uses item.size_bytes when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
                mock_client = Mock(spec=SupabaseClient)
                mock_client.get_or_create_experiment.return_value = "exp_123"
                mock_client.upload_file.return_value = (
                    "https://storage.url/file",
                    "checksum123",
                )
                mock_client_class.return_value = mock_client

                handler = SyncHandler("test_exp", "/test/path")

                item = SyncItem(
                    id="sync_1",
                    job_id="job_1",
                    file_path=str(test_file),
                    file_type="log",
                    metadata={},
                    created_at=datetime.now(UTC).isoformat(),
                    size_bytes=999,  # Different from actual file size
                )

                handler.sync_file(item)

                # Should use item.size_bytes in create_sync_status
                mock_client.create_sync_status.assert_called_once()
                call_args = mock_client.create_sync_status.call_args[1]
                assert call_args["size_bytes"] == 999

    def test_sync_job_data_success(self) -> None:
        """Test successful job data sync."""
        with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
            mock_client = Mock(spec=SupabaseClient)
            mock_client.get_or_create_experiment.return_value = "exp_123"
            mock_client.sync_job.return_value = True
            mock_client_class.return_value = mock_client

            handler = SyncHandler("test_exp", "/test/path")

            job_data = {
                "id": "job_1",
                "status": "completed",
                "config": {"param": "value"},
            }

            result = handler.sync_job_data(job_data)

            assert result is True
            mock_client.sync_job.assert_called_once_with(job_data, "exp_123")

    def test_sync_job_data_disabled(self) -> None:
        """Test sync_job_data when sync is disabled."""
        with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
            mock_client_class.side_effect = Exception("No connection")

            handler = SyncHandler("test_exp", "/test/path")

            job_data = {"id": "job_1"}
            result = handler.sync_job_data(job_data)

            assert result is False

    def test_sync_job_data_no_experiment_id(self) -> None:
        """Test sync_job_data when experiment_id is None."""
        with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
            mock_client = Mock(spec=SupabaseClient)
            mock_client.get_or_create_experiment.return_value = None
            mock_client_class.return_value = mock_client

            handler = SyncHandler("test_exp", "/test/path")

            job_data = {"id": "job_1"}
            result = handler.sync_job_data(job_data)

            assert result is False

    def test_sync_job_data_failure(self) -> None:
        """Test sync_job_data when sync fails."""
        with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
            mock_client = Mock(spec=SupabaseClient)
            mock_client.get_or_create_experiment.return_value = "exp_123"
            mock_client.sync_job.side_effect = Exception("Sync failed")
            mock_client_class.return_value = mock_client

            handler = SyncHandler("test_exp", "/test/path")

            job_data = {"id": "job_1"}

            with patch("builtins.print") as mock_print:
                result = handler.sync_job_data(job_data)

                assert result is False
                mock_print.assert_called_with(
                    "[SyncHandler] Failed to sync job job_1: Sync failed"
                )

    def test_is_available_success(self) -> None:
        """Test is_available when connection works."""
        with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
            mock_client = Mock(spec=SupabaseClient)
            mock_client.get_or_create_experiment.return_value = "exp_123"
            mock_client.test_connection.return_value = True
            mock_client_class.return_value = mock_client

            handler = SyncHandler("test_exp", "/test/path")

            assert handler.is_available() is True
            mock_client.test_connection.assert_called_once()

    def test_is_available_disabled(self) -> None:
        """Test is_available when sync is disabled."""
        with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
            mock_client_class.side_effect = Exception("No connection")

            handler = SyncHandler("test_exp", "/test/path")

            assert handler.is_available() is False

    def test_is_available_connection_fails(self) -> None:
        """Test is_available when test_connection fails."""
        with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
            mock_client = Mock(spec=SupabaseClient)
            mock_client.get_or_create_experiment.return_value = "exp_123"
            mock_client.test_connection.side_effect = Exception(
                "Connection test failed"
            )
            mock_client_class.return_value = mock_client

            handler = SyncHandler("test_exp", "/test/path")

            assert handler.is_available() is False

    def test_sync_file_sync_status_creation_failure(self) -> None:
        """Test sync_file when sync status creation fails but upload succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            with patch("dr_exp.sync.sync_handler.SupabaseClient") as mock_client_class:
                mock_client = Mock(spec=SupabaseClient)
                mock_client.get_or_create_experiment.return_value = "exp_123"
                mock_client.upload_file.return_value = (
                    "https://storage.url/file",
                    "checksum123",
                )
                mock_client.create_sync_status.side_effect = Exception("DB error")
                mock_client_class.return_value = mock_client

                handler = SyncHandler("test_exp", "/test/path")

                item = SyncItem(
                    id="sync_1",
                    job_id="job_1",
                    file_path=str(test_file),
                    file_type="log",
                    metadata={},
                    created_at=datetime.now(UTC).isoformat(),
                )

                # Should raise exception when sync status creation fails
                with pytest.raises(Exception, match="DB error"):
                    handler.sync_file(item)

                # Upload should have been called
                mock_client.upload_file.assert_called_once()
                mock_client.create_sync_status.assert_called_once()
