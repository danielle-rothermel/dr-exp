"""Test that Step 0 cleanup was successful."""
import os
import pytest
from pathlib import Path


def test_old_directories_removed():
    """Verify old directories have been deleted."""
    old_dirs = [
        "src/dr_exp/job_db",
        "src/dr_exp/manage", 
        "src/dr_exp/cli"
    ]
    
    for dir_path in old_dirs:
        assert not os.path.exists(dir_path), f"Directory should be deleted: {dir_path}"


def test_old_files_removed():
    """Verify old files have been deleted."""
    old_files = [
        "src/dr_exp/utils/factory.py",
        "src/dr_exp/utils/jobdb_factory.py",
        "src/dr_exp/utils/cli_config.py",
        "scripts/run_worker.py",
        "scripts/run_manager.py",
        "scripts/upload_configs.py",
        "scripts/reset_local_jobdb.py"
    ]
    
    for file_path in old_files:
        assert not os.path.exists(file_path), f"File should be deleted: {file_path}"


def test_new_directories_created():
    """Verify new directories exist with __init__.py files."""
    new_dirs = [
        "src/dr_exp/core",
        "src/dr_exp/sync",
        "src/dr_exp/worker",
        "tests/implementation"
    ]
    
    for dir_path in new_dirs:
        assert os.path.exists(dir_path), f"Directory should exist: {dir_path}"
        init_file = os.path.join(dir_path, "__init__.py")
        assert os.path.exists(init_file), f"Missing __init__.py in: {dir_path}"


def test_remaining_structure():
    """Verify important directories were kept."""
    kept_dirs = [
        "src/dr_exp/api",
        "src/dr_exp/logging",
        "src/dr_exp/training",
        "src/dr_exp/utils"
    ]
    
    for dir_path in kept_dirs:
        assert os.path.exists(dir_path), f"Directory should still exist: {dir_path}"