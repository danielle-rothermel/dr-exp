import pytest
from pathlib import Path

def test_documentation_files_exist():
    docs_dir = Path("docs")
    assert (docs_dir / "quick_start_guide.md").exists()
    assert (docs_dir / "agent_debug_sequence.md").exists()
    
def test_no_worker_log_references():
    # Ensure we removed worker log references
    quick_start = Path("docs/quick_start_guide.md").read_text()
    assert "worker_debug_worker.log" not in quick_start
    assert "tail -f" not in quick_start or "worker.log" in quick_start
    
def test_correct_run_one_syntax():
    # Ensure run-one uses job ID
    quick_start = Path("docs/quick_start_guide.md").read_text()
    assert "run-one" in quick_start
    assert "configs/test_job.yaml" not in quick_start.split("run-one")[1].split("\n")[0]
    
def test_error_file_format():
    # Ensure error.txt not error.json
    quick_start = Path("docs/quick_start_guide.md").read_text()
    assert "error.json" not in quick_start
    assert "error.txt" in quick_start