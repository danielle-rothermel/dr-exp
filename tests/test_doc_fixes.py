"""Tests for documentation generation fixes."""

from pathlib import Path


def test_documentation_files_exist() -> None:
    docs_dir = Path("docs")
    assert (docs_dir / "quick_start_guide.md").exists()
    assert (docs_dir / "agent_debug_sequence.md").exists()


def test_no_worker_log_references() -> None:
    # Ensure we removed worker log references
    quick_start = Path("docs/quick_start_guide.md").read_text()
    assert "worker_debug_worker.log" not in quick_start
    assert "tail -f" not in quick_start or "worker.log" in quick_start


def test_correct_run_one_syntax() -> None:
    # Ensure run-one uses job ID
    quick_start = Path("docs/quick_start_guide.md").read_text()
    assert "run-one" in quick_start
    assert "configs/test_job.yaml" not in quick_start.split("run-one")[1].split("\n")[0]


def test_error_file_format() -> None:
    # Ensure error.txt not error.json
    quick_start = Path("docs/quick_start_guide.md").read_text()
    assert "error.json" not in quick_start
    assert "error.txt" in quick_start


def test_submit_command_syntax() -> None:
    # Ensure submit commands use --config-path and --config-name
    debug_seq = Path("docs/agent_debug_sequence.md").read_text()
    # Check that we don't have old submit syntax
    assert "submit configs/test_job.yaml" not in debug_seq
    assert "submit configs/decon_config.yaml" not in debug_seq
    # Check that we have new syntax
    assert "submit --config-path configs --config-name test_job" in debug_seq
    assert "submit --config-path configs --config-name decon_config" in debug_seq


def test_error_format_in_debug_sequence() -> None:
    # Ensure error.txt in debug sequence
    debug_seq = Path("docs/agent_debug_sequence.md").read_text()
    assert "error.json" not in debug_seq
    assert "error.txt" in debug_seq
