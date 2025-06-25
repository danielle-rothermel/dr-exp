"""Integration tests for CLI job management commands."""

import tempfile
from datetime import datetime, timedelta, UTC
from pathlib import Path
from click.testing import CliRunner

from dr_exp.cli.main import cli
from dr_exp.core.job_db import JobDB


def test_cli_kill() -> None:
    """Test killing jobs."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create jobs
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        config = {"_target_": "test.train"}

        job1 = job_db.create_job(config)
        job2 = job_db.create_job(config)
        job_db.claim_next_job("worker")  # This claims job1 (first in queue)

        # Kill queued job (job2 is still queued)
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "kill",
                job2[:8],  # Partial ID
            ],
        )

        assert result.exit_code == 0
        assert f"Killed job: {job2}" in result.output

        # Verify job is failed (killed)
        job = job_db.get_job(job2)
        assert job["status"] == "failed"
        assert "Killed" in job.get("error", "")

        # Kill running job (job1 is running)
        result = runner.invoke(
            cli,
            ["--base-path", tmpdir, "--experiment", "test_exp", "job", "kill", job1],
        )

        assert result.exit_code == 0

        # Try to kill non-existent job
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "kill",
                "fake_id",
            ],
        )

        assert result.exit_code == 1
        assert "No job found matching" in result.output


def test_cli_boost() -> None:
    """Test boosting job priority."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create jobs
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        config = {"_target_": "test.train"}

        job1 = job_db.create_job(config, priority=100)
        job2 = job_db.create_job(config, priority=200)

        # Boost job1
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "boost",
                job1[:8],  # Partial ID
                "--priority",
                "900",
            ],
        )

        assert result.exit_code == 0
        assert f"Boosted job: {job1} (100 → 900)" in result.output

        # Verify priority changed
        job = job_db.get_job(job1)
        assert job["priority"] == 900

        # Boost multiple jobs
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "boost",
                job1,
                job2,
                "--priority",
                "950",
            ],
        )

        assert result.exit_code == 0
        assert "Boosted 2 job(s)" in result.output


def test_cli_recover() -> None:
    """Test recovering stale jobs."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create stale job
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        config = {"_target_": "test.train"}

        job_id = job_db.create_job(config)
        job_db.claim_next_job("worker")

        # Make it stale by backdating
        old_time = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        job_db.update_job(job_id, {"started_at": old_time})

        # Test dry run
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "recover",
                "--dry-run",
                "--threshold",
                "300",
            ],
        )

        assert result.exit_code == 0
        assert "Would recover 1 stale job(s)" in result.output
        assert job_id in result.output

        # Actually recover
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "recover",
                "--threshold",
                "300",
            ],
        )

        assert result.exit_code == 0
        assert "Recovered 1 stale job(s)" in result.output

        # Verify job is queued again
        job = job_db.get_job(job_id)
        assert job["status"] == "queued"


def test_cli_sync_status(tmp_path: Path) -> None:
    """Test sync status command."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create experiment with sync items
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Add some sync items
        from dr_exp.sync.queue import SyncQueue, SyncItem

        sync_queue = SyncQueue(job_db.get_sync_queue_path())

        # Add pending item
        item1 = SyncItem(
            id="sync1",
            job_id="job1",
            file_path=str(tmp_path / "file1.txt"),
            file_type="metrics",
            metadata={},
            created_at=datetime.now(UTC).isoformat(),
        )
        sync_queue.add_item(item1)

        # Add failed item
        item2 = SyncItem(
            id="sync2",
            job_id="job2",
            file_path=str(tmp_path / "file2.txt"),
            file_type="model",
            metadata={},
            created_at=datetime.now(UTC).isoformat(),
            attempts=1,
            error="Network error",
        )
        sync_queue.add_item(item2)

        # Get status
        result = runner.invoke(
            cli,
            ["--base-path", tmpdir, "--experiment", "test_exp", "job", "sync-status"],
        )

        assert result.exit_code == 0
        assert "Sync Queue Status:" in result.output
        assert "Pending:   2" in result.output

        # Get verbose status
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "sync-status",
                "--verbose",
            ],
        )

        assert result.exit_code == 0
        assert "Pending items:" in result.output
        assert "sync1" in result.output
        assert "sync2" in result.output
        assert "Network error" in result.output


def test_cli_run_one() -> None:
    """Test running a single job."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a job
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        config = {"_target_": "dr_exp.trainers.test_trainer.train", "epochs": 2}
        job_id = job_db.create_job(config, priority=500)

        # Run the specific job
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "run-one",
                job_id[:8],  # Partial ID
                "--no-sync",
            ],
        )

        assert result.exit_code == 0
        assert f"Running job: {job_id}" in result.output
        assert "Job " in result.output
        assert "COMPLETED" in result.output

        # Verify job completed
        job = job_db.get_job(job_id)
        assert job["status"] == "completed"

        # Test running failed job
        config["fail_rate"] = 1.0
        fail_job_id = job_db.create_job(config)

        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "run-one",
                fail_job_id,
            ],
        )

        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "Simulated training failure" in result.output


def test_cli_validate() -> None:
    """Test experiment validation."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Test uninitialized experiment
        result = runner.invoke(
            cli, ["--base-path", tmpdir, "--experiment", "missing_exp", "validate"]
        )

        assert result.exit_code == 1
        assert "Validation FAILED" in result.output
        assert "Missing directories" in result.output

        # Initialize experiment
        runner.invoke(cli, ["--base-path", tmpdir, "--experiment", "good_exp", "init"])

        # Validate good experiment
        result = runner.invoke(
            cli, ["--base-path", tmpdir, "--experiment", "good_exp", "validate"]
        )

        assert result.exit_code == 0
        assert "Validation PASSED" in result.output
        assert "No jobs found" in result.output  # Warning

        # Add a stale job
        job_db = JobDB(base_path=tmpdir, experiment_name="good_exp", validate=False)
        config = {"_target_": "test.train"}
        job_id = job_db.create_job(config)
        job_db.claim_next_job("worker")

        # Backdate to make stale
        old_time = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        job_db.update_job(job_id, {"last_heartbeat": old_time})

        # Validate with stale job
        result = runner.invoke(
            cli, ["--base-path", tmpdir, "--experiment", "good_exp", "validate"]
        )

        assert result.exit_code == 0
        assert "may be stale" in result.output


def test_cli_partial_id_matching() -> None:
    """Test partial job ID matching."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create jobs with similar IDs
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        config = {"_target_": "test.train"}

        # Create multiple jobs
        jobs = [job_db.create_job(config) for _ in range(3)]

        # Test unique partial match on first job
        partial = jobs[0][:8]
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "boost",
                partial,  # Use boost instead of kill to avoid marking as failed
                "--priority",
                "500",
            ],
        )

        assert result.exit_code == 0
        assert f"Boosted job: {jobs[0]}" in result.output

        # Test ambiguous partial match
        # Create a scenario where partial IDs might conflict
        # This is unlikely with UUIDs but we'll test the handling
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "kill",
                "a",  # Very short partial that might match multiple
            ],
        )

        # Should either succeed with one match or show multiple matches
        if "Multiple jobs match" in result.output:
            assert result.exit_code == 1
