"""Test that Step 0 cleanup was successful."""

from pathlib import Path


def test_old_directories_removed() -> None:
    """Verify old directories have been deleted."""
    old_dirs = [
        "src/dr_exp/job_db",
        "src/dr_exp/manage",
    ]  # CLI still exists but simplified

    for dir_path in old_dirs:
        assert not Path(dir_path).exists(), f"Directory should be deleted: {dir_path}"


def test_old_files_removed() -> None:
    """Verify old files have been deleted."""
    old_files = [
        "src/dr_exp/utils/factory.py",
        "src/dr_exp/utils/jobdb_factory.py",
        "src/dr_exp/utils/cli_config.py",
        "scripts/run_worker.py",
        "scripts/run_manager.py",
        "scripts/upload_configs.py",
        "scripts/reset_local_jobdb.py",
    ]

    for file_path in old_files:
        assert not Path(file_path).exists(), f"File should be deleted: {file_path}"


def test_new_directories_created() -> None:
    """Verify new directories exist with __init__.py files."""
    new_dirs = [
        "src/dr_exp/core",
        "src/dr_exp/sync",
        "src/dr_exp/worker",
        "tests/implementation",
    ]

    for dir_path in new_dirs:
        assert Path(dir_path).exists(), f"Directory should exist: {dir_path}"
        init_file = Path(dir_path) / "__init__.py"
        assert init_file.exists(), f"Missing __init__.py in: {dir_path}"


def test_remaining_structure() -> None:
    """Verify important directories were kept."""
    kept_dirs = [
        "src/dr_exp/utils",  # Only utils remains from original dirs
        "src/dr_exp/core",  # New core module
        "src/dr_exp/cli",  # Simplified CLI
    ]

    for dir_path in kept_dirs:
        assert Path(dir_path).exists(), f"Directory should still exist: {dir_path}"
