"""Validation tests for documentation accuracy."""

from pathlib import Path


def test_documentation_files_exist() -> None:
    docs_dir = Path("docs")
    assert (docs_dir / "quick_start_guide.md").exists()
    assert (docs_dir / "project_workflows.md").exists()


def test_readme_describes_local_first_system() -> None:
    readme = Path("README.md").read_text()
    assert "sync_queue" not in readme
    assert "Remote Monitoring" not in readme
    assert "Known issues" in readme
    assert "## Direction" in readme


def test_no_remote_monitoring_in_quick_start() -> None:
    quick_start = Path("docs/quick_start_guide.md").read_text()
    assert "sync_queue" not in quick_start
    assert "FastAPI" not in quick_start
