# Phase 6: Migration and Cleanup Implementation Guide

## Overview
This phase implements tools for migrating existing experiments (if any) and comprehensive cleanup utilities.

**Duration**: 2 days
**Prerequisite**: Phases 1-4 complete (Phase 5 optional)
**Outcome**: Clean migration path and storage management tools

## Part A: Migration Tools (Skip if Fresh Start)

Since you indicated there's no existing data to preserve, this section is provided for completeness but can be skipped.

### Migration Script Template

Create `src/dr_exp/tools/migrate.py`:

```python
"""Migration tool for old experiment data (if needed)."""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, Any

from dr_exp.core.job_db import JobDB


def migrate_old_experiment(
    old_path: str,
    new_base_path: str, 
    experiment_name: str,
    dry_run: bool = True
) -> None:
    """Migrate old experiment data to new structure.
    
    Args:
        old_path: Path to old experiment data
        new_base_path: New base path for experiments
        experiment_name: Name for the migrated experiment
        dry_run: If True, only show what would be done
    """
    print(f"Migration plan: {old_path} -> {new_base_path}/{experiment_name}")
    
    if dry_run:
        print("DRY RUN - no changes will be made")
    
    # This is a template - implement based on your old structure
    # Example for old structure: old_path/job_data/*.json
    
    old_jobs_dir = Path(old_path) / "job_data"
    if not old_jobs_dir.exists():
        print(f"No job_data found at {old_jobs_dir}")
        return
    
    # Count jobs
    job_files = list(old_jobs_dir.glob("*.json"))
    print(f"Found {len(job_files)} jobs to migrate")
    
    if not dry_run:
        # Initialize new JobDB
        db = JobDB(base_path=new_base_path, experiment_name=experiment_name)
        
        # Migrate each job
        for job_file in job_files:
            with open(job_file, 'r') as f:
                old_job = json.load(f)
            
            # Transform old format to new format
            # Adjust this based on your old schema
            new_job_id = old_job.get("id", job_file.stem)
            config = old_job.get("config_json", old_job.get("config", {}))
            
            # Create in new structure
            db.create_job(config, priority=old_job.get("priority", 100))
            print(f"Migrated job {new_job_id}")
```

## Part B: Cleanup Tools (Primary Focus)

### Step 1: Implement Storage Scanner

Create `src/dr_exp/tools/storage_scanner.py`:

```python
"""Storage scanner for experiment cleanup."""

import os
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from collections import defaultdict

from dr_exp.core.job_db import JobDB


class StorageScanner:
    """Scan and analyze experiment storage usage."""
    
    def __init__(self, base_path: str):
        """Initialize scanner.
        
        Args:
            base_path: Base directory containing experiments
        """
        self.base_path = Path(base_path)
        if not self.base_path.exists():
            raise ValueError(f"Base path does not exist: {base_path}")
    
    def scan_all_experiments(self) -> Dict[str, Dict]:
        """Scan all experiments and return storage summary.
        
        Returns:
            Dictionary mapping experiment names to their stats
        """
        results = {}
        
        # Find all experiment directories
        for exp_dir in self.base_path.iterdir():
            if exp_dir.is_dir() and not exp_dir.name.startswith('.'):
                exp_stats = self.scan_experiment(exp_dir)
                if exp_stats['total_size'] > 0:  # Only include non-empty experiments
                    results[exp_dir.name] = exp_stats
        
        return results
    
    def scan_experiment(self, exp_path: Path) -> Dict:
        """Scan a single experiment directory.
        
        Args:
            exp_path: Path to experiment directory
            
        Returns:
            Statistics about the experiment
        """
        stats = {
            'path': str(exp_path),
            'total_size': 0,
            'job_count': 0,
            'storage_breakdown': defaultdict(int),
            'oldest_file': None,
            'newest_file': None,
        }
        
        # Scan jobs directory
        jobs_dir = exp_path / "jobs"
        if jobs_dir.exists():
            job_files = list(jobs_dir.glob("*.json"))
            stats['job_count'] = len(job_files)
            
            for job_file in job_files:
                stats['total_size'] += job_file.stat().st_size
                stats['storage_breakdown']['jobs'] += job_file.stat().st_size
                self._update_timestamps(stats, job_file)
        
        # Scan storage directory
        storage_dir = exp_path / "storage"
        if storage_dir.exists():
            for root, dirs, files in os.walk(storage_dir):
                for file in files:
                    file_path = Path(root) / file
                    size = file_path.stat().st_size
                    stats['total_size'] += size
                    
                    # Categorize by file type
                    if file.endswith('.jsonl'):
                        stats['storage_breakdown']['metrics'] += size
                    elif file.endswith('.log'):
                        stats['storage_breakdown']['logs'] += size
                    elif file.endswith('.pt') or file.endswith('.pth'):
                        stats['storage_breakdown']['models'] += size
                    else:
                        stats['storage_breakdown']['other'] += size
                    
                    self._update_timestamps(stats, file_path)
        
        # Scan sync queue
        sync_dir = exp_path / "sync_queue"
        if sync_dir.exists():
            sync_files = list(sync_dir.glob("*.json"))
            stats['pending_syncs'] = len(sync_files)
            for sync_file in sync_files:
                stats['total_size'] += sync_file.stat().st_size
                stats['storage_breakdown']['sync_queue'] += sync_file.stat().st_size
        
        return stats
    
    def _update_timestamps(self, stats: Dict, file_path: Path) -> None:
        """Update oldest/newest file timestamps."""
        mtime = file_path.stat().st_mtime
        
        if stats['oldest_file'] is None or mtime < stats['oldest_file'][1]:
            stats['oldest_file'] = (str(file_path), mtime)
        
        if stats['newest_file'] is None or mtime > stats['newest_file'][1]:
            stats['newest_file'] = (str(file_path), mtime)
    
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format bytes as human-readable string."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def print_summary(self, results: Dict[str, Dict]) -> None:
        """Print a formatted summary of scan results."""
        total_size = sum(exp['total_size'] for exp in results.values())
        total_jobs = sum(exp['job_count'] for exp in results.values())
        
        print(f"\nStorage Summary for {self.base_path}")
        print("=" * 80)
        print(f"Total experiments: {len(results)}")
        print(f"Total jobs: {total_jobs}")
        print(f"Total size: {self.format_size(total_size)}")
        print()
        
        # Sort by size
        sorted_exps = sorted(results.items(), key=lambda x: x[1]['total_size'], reverse=True)
        
        for exp_name, stats in sorted_exps:
            print(f"\nExperiment: {exp_name}")
            print(f"  Path: {stats['path']}")
            print(f"  Total size: {self.format_size(stats['total_size'])}")
            print(f"  Jobs: {stats['job_count']}")
            
            if stats['pending_syncs']:
                print(f"  ⚠️  Pending syncs: {stats['pending_syncs']}")
            
            print("  Storage breakdown:")
            for category, size in stats['storage_breakdown'].items():
                print(f"    - {category}: {self.format_size(size)}")
            
            if stats['oldest_file']:
                oldest_date = datetime.fromtimestamp(stats['oldest_file'][1]).strftime('%Y-%m-%d')
                print(f"  Oldest file: {oldest_date}")
            
            if stats['newest_file']:
                newest_date = datetime.fromtimestamp(stats['newest_file'][1]).strftime('%Y-%m-%d')
                print(f"  Newest file: {newest_date}")
```

### Step 2: Implement Interactive Cleanup Tool

Create `src/dr_exp/tools/cleanup.py`:

```python
"""Interactive cleanup tool for experiment storage."""

import os
import shutil
from pathlib import Path
from typing import List, Set, Optional
import json

from dr_exp.tools.storage_scanner import StorageScanner
from dr_exp.core.job_db import JobDB


class InteractiveCleaner:
    """Interactive tool for cleaning experiment storage."""
    
    def __init__(self, base_path: str, dry_run: bool = False):
        """Initialize cleaner.
        
        Args:
            base_path: Base directory containing experiments
            dry_run: If True, don't actually delete anything
        """
        self.base_path = Path(base_path)
        self.scanner = StorageScanner(base_path)
        self.dry_run = dry_run
        
        if dry_run:
            print("🔍 DRY RUN MODE - No files will be deleted")
    
    def run(self) -> None:
        """Run interactive cleanup process."""
        print("Scanning experiments...")
        results = self.scanner.scan_all_experiments()
        
        if not results:
            print("No experiments found!")
            return
        
        self.scanner.print_summary(results)
        
        while True:
            print("\n" + "=" * 80)
            print("Cleanup Options:")
            print("1. Clean specific experiment")
            print("2. Clean experiments older than N days")
            print("3. Clean completed experiments only")
            print("4. Clean all experiments (dangerous!)")
            print("5. Show summary again")
            print("0. Exit")
            
            choice = input("\nSelect option (0-5): ").strip()
            
            if choice == '0':
                break
            elif choice == '1':
                self._clean_specific(results)
            elif choice == '2':
                self._clean_by_age(results)
            elif choice == '3':
                self._clean_completed(results)
            elif choice == '4':
                self._clean_all(results)
            elif choice == '5':
                self.scanner.print_summary(results)
            else:
                print("Invalid option")
    
    def _clean_specific(self, results: Dict[str, Dict]) -> None:
        """Clean a specific experiment."""
        exp_names = sorted(results.keys())
        
        print("\nAvailable experiments:")
        for i, name in enumerate(exp_names, 1):
            size = self.scanner.format_size(results[name]['total_size'])
            print(f"{i}. {name} ({size})")
        
        try:
            idx = int(input("\nSelect experiment number: ")) - 1
            if 0 <= idx < len(exp_names):
                exp_name = exp_names[idx]
                self._confirm_and_clean(exp_name, results[exp_name])
            else:
                print("Invalid selection")
        except ValueError:
            print("Invalid input")
    
    def _clean_by_age(self, results: Dict[str, Dict]) -> None:
        """Clean experiments older than specified days."""
        try:
            days = int(input("\nDelete experiments older than how many days? "))
            cutoff_time = time.time() - (days * 86400)
            
            old_experiments = []
            for exp_name, stats in results.items():
                if stats['newest_file'] and stats['newest_file'][1] < cutoff_time:
                    old_experiments.append((exp_name, stats))
            
            if not old_experiments:
                print(f"No experiments older than {days} days")
                return
            
            print(f"\nFound {len(old_experiments)} experiments older than {days} days:")
            total_size = 0
            for exp_name, stats in old_experiments:
                size = stats['total_size']
                total_size += size
                print(f"  - {exp_name} ({self.scanner.format_size(size)})")
            
            print(f"\nTotal size to clean: {self.scanner.format_size(total_size)}")
            
            if self._confirm(f"Delete all {len(old_experiments)} old experiments?"):
                for exp_name, stats in old_experiments:
                    self._delete_experiment(exp_name, stats['path'])
                    
        except ValueError:
            print("Invalid input")
    
    def _clean_completed(self, results: Dict[str, Dict]) -> None:
        """Clean only experiments with all jobs completed."""
        completed_experiments = []
        
        for exp_name, stats in results.items():
            # Check if all jobs are completed
            exp_path = Path(stats['path'])
            db = JobDB(base_path=str(self.base_path), experiment_name=exp_name)
            
            jobs = db.list_jobs()
            if jobs and all(job['status'] in ['completed', 'failed'] for job in jobs):
                # Check if synced to Supabase
                has_pending = stats.get('pending_syncs', 0) > 0
                completed_experiments.append((exp_name, stats, has_pending))
        
        if not completed_experiments:
            print("No fully completed experiments found")
            return
        
        print(f"\nFound {len(completed_experiments)} completed experiments:")
        for exp_name, stats, has_pending in completed_experiments:
            size = self.scanner.format_size(stats['total_size'])
            pending_warn = " ⚠️  (has pending syncs)" if has_pending else ""
            print(f"  - {exp_name} ({size}){pending_warn}")
        
        if self._confirm("Delete all completed experiments?"):
            for exp_name, stats, _ in completed_experiments:
                self._delete_experiment(exp_name, stats['path'])
    
    def _clean_all(self, results: Dict[str, Dict]) -> None:
        """Clean all experiments (with strong confirmation)."""
        total_size = sum(exp['total_size'] for exp in results.values())
        
        print(f"\n⚠️  WARNING: This will delete ALL {len(results)} experiments!")
        print(f"Total size: {self.scanner.format_size(total_size)}")
        
        if self._confirm("Are you SURE you want to delete everything?", require_yes=True):
            if self._confirm("This is irreversible. Type 'yes' to confirm: ", require_yes=True):
                for exp_name, stats in results.items():
                    self._delete_experiment(exp_name, stats['path'])
    
    def _confirm_and_clean(self, exp_name: str, stats: Dict) -> None:
        """Confirm and clean a single experiment."""
        print(f"\nExperiment: {exp_name}")
        print(f"Size: {self.scanner.format_size(stats['total_size'])}")
        print(f"Jobs: {stats['job_count']}")
        
        if stats.get('pending_syncs', 0) > 0:
            print(f"⚠️  Warning: {stats['pending_syncs']} pending sync operations")
        
        if self._confirm(f"Delete experiment '{exp_name}'?"):
            self._delete_experiment(exp_name, stats['path'])
    
    def _confirm(self, prompt: str, require_yes: bool = False) -> bool:
        """Get user confirmation."""
        if require_yes:
            response = input(f"{prompt} ").strip().lower()
            return response == 'yes'
        else:
            response = input(f"{prompt} (y/N) ").strip().lower()
            return response in ['y', 'yes']
    
    def _delete_experiment(self, exp_name: str, exp_path: str) -> None:
        """Delete an experiment directory."""
        if self.dry_run:
            print(f"[DRY RUN] Would delete: {exp_path}")
        else:
            try:
                shutil.rmtree(exp_path)
                print(f"✓ Deleted: {exp_name}")
            except Exception as e:
                print(f"❌ Failed to delete {exp_name}: {e}")
```

### Step 3: Create CLI Entry Points

Create `cleanup_experiments.py`:

```python
#!/usr/bin/env python3
"""Command-line tool for experiment cleanup."""

import argparse
import sys
from pathlib import Path

from dr_exp.tools.storage_scanner import StorageScanner
from dr_exp.tools.cleanup import InteractiveCleaner


def main():
    parser = argparse.ArgumentParser(
        description="Scan and clean experiment storage"
    )
    parser.add_argument(
        "base_path",
        help="Base directory containing experiments"
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Only scan and report, don't offer cleanup"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Non-interactive mode - just show summary"
    )
    
    args = parser.parse_args()
    
    # Validate base path
    base_path = Path(args.base_path)
    if not base_path.exists():
        print(f"Error: Base path does not exist: {base_path}")
        sys.exit(1)
    
    if args.scan_only or args.non_interactive:
        # Just scan and show summary
        scanner = StorageScanner(args.base_path)
        results = scanner.scan_all_experiments()
        scanner.print_summary(results)
    else:
        # Interactive cleanup
        cleaner = InteractiveCleaner(args.base_path, dry_run=args.dry_run)
        cleaner.run()


if __name__ == "__main__":
    main()
```

## Step 4: Create Pytest Tests

Create `tests/test_cleanup_tools.py`:

```python
"""Test cleanup tools.

⚠️ These tests verify storage management functionality.
If they fail, the cleanup tools have bugs.
DO NOT modify tests - fix the implementation.
"""

import time
import os
from pathlib import Path
import pytest

from dr_exp.core.job_db import JobDB
from dr_exp.tools.storage_scanner import StorageScanner
from dr_exp.tools.cleanup import InteractiveCleaner


@pytest.fixture
def cleanup_test_env(tmp_path):
    """Create test environment with multiple experiments."""
    base_path = tmp_path / "experiments"
    base_path.mkdir()
    
    # Create multiple test experiments
    experiments = ["exp_old", "exp_recent", "exp_active"]
    
    for i, exp_name in enumerate(experiments):
        db = JobDB(base_path=str(base_path), experiment_name=exp_name)
        
        # Create and run some jobs
        for j in range(2):
            job_id = db.create_job({
                "_target_": "test.train",
                "model": f"model_{j}"
            }, priority=100)
            
            # Create some fake outputs
            storage_path = db.get_storage_path(job_id)
            (storage_path / "metrics.jsonl").write_text('{"loss": 0.5}\n' * 10)
            (storage_path / "model.pt").write_text("fake model data" * 1000)
            (storage_path / "training.log").write_text("training log\n" * 100)
            
            # Update job status
            if exp_name != "exp_active":  # Keep active exp with running jobs
                db.update_job(job_id, {"status": "completed"})
        
        # Make exp_old appear older
        if exp_name == "exp_old":
            old_time = time.time() - (10 * 86400)  # 10 days ago
            for file in Path(db.experiment_path).rglob("*"):
                if file.is_file():
                    os.utime(file, (old_time, old_time))
    
    return base_path, experiments


def test_storage_scanner(cleanup_test_env):
    """Test storage scanner functionality."""
    base_path, experiments = cleanup_test_env
    
    scanner = StorageScanner(str(base_path))
    results = scanner.scan_all_experiments()
    
    # Verify all experiments found
    assert len(results) == 3
    for exp_name in experiments:
        assert exp_name in results
        assert results[exp_name]['job_count'] == 2
        assert results[exp_name]['total_size'] > 0


def test_storage_scanner_size_calculation(cleanup_test_env):
    """Test accurate size calculation."""
    base_path, _ = cleanup_test_env
    
    scanner = StorageScanner(str(base_path))
    results = scanner.scan_all_experiments()
    
    # Each experiment should have predictable size
    for exp_name, info in results.items():
        # We created specific files with known sizes
        assert info['total_size'] > 1000  # At least 1KB
        assert 'metrics' in info['by_category']
        assert 'models' in info['by_category']
        assert 'logs' in info['by_category']


def test_cleanup_dry_run(cleanup_test_env):
    """Test cleanup in dry-run mode."""
    base_path, experiments = cleanup_test_env
    
    cleaner = InteractiveCleaner(str(base_path), dry_run=True)
    
    # Get experiments older than 5 days
    old_experiments = cleaner.get_experiments_older_than(5)
    
    # Should find exp_old (10 days old)
    exp_names = [exp['name'] for exp in old_experiments]
    assert "exp_old" in exp_names
    assert "exp_recent" not in exp_names
    assert "exp_active" not in exp_names


def test_cleanup_completed_jobs(cleanup_test_env):
    """Test cleaning completed jobs."""
    base_path, _ = cleanup_test_env
    
    cleaner = InteractiveCleaner(str(base_path), dry_run=True)
    
    # Test finding completed experiments
    completed = cleaner.get_completed_experiments()
    
    # exp_old and exp_recent have all completed jobs
    exp_names = [exp['name'] for exp in completed]
    assert "exp_old" in exp_names
    assert "exp_recent" in exp_names
    assert "exp_active" not in exp_names  # Has running jobs


@pytest.mark.parametrize("days,expected_count", [
    (15, 0),  # Nothing older than 15 days
    (5, 1),   # Only exp_old
    (0, 3),   # All experiments
])
def test_age_based_filtering(cleanup_test_env, days, expected_count):
    """Test filtering experiments by age."""
    base_path, _ = cleanup_test_env
    
    cleaner = InteractiveCleaner(str(base_path), dry_run=True)
    old_experiments = cleaner.get_experiments_older_than(days)
    
    assert len(old_experiments) == expected_count


def test_migration_dry_run(tmp_path):
    """Test migration tool in dry-run mode.
    
    ⚠️ This test verifies migration logic.
    Migration must preserve all job data.
    """
    # Create old-style experiment structure
    old_path = tmp_path / "old_experiment"
    old_jobs_dir = old_path / "job_data"
    old_jobs_dir.mkdir(parents=True)
    
    # Create some old job files
    for i in range(3):
        job_data = {
            "id": f"job_{i}",
            "config": {"model": f"model_{i}"},
            "priority": 100 + i * 100,
            "status": "completed"
        }
        with open(old_jobs_dir / f"job_{i}.json", "w") as f:
            json.dump(job_data, f)
    
    # Test migration
    from dr_exp.tools.migrate import migrate_old_experiment
    
    new_base = tmp_path / "new_experiments"
    new_base.mkdir()
    
    # Dry run first
    migrate_old_experiment(
        str(old_path),
        str(new_base),
        "migrated_exp",
        dry_run=True
    )
    
    # Should not create anything in dry run
    assert not (new_base / "migrated_exp").exists()
        
```

## Step 5: Run Tests with Quality Gates

### Validation Gate
Run these commands and fix ALL issues before proceeding:

```bash
# 1. Code quality check
ckdr
# Expected: "All checks passed!"
# If fails: Fix the code, not the rules

# 2. Run all tests
pt
# Expected: All tests pass, no skips
# If fails: Fix implementation, not tests

# 3. Run cleanup tests specifically
pt tests/test_cleanup_tools.py -v
# Expected: All cleanup tests pass
```

⚠️ **CRITICAL**: If any check fails:
1. Read the FULL error message
2. Understand what the test/check expects
3. Fix YOUR CODE to meet expectations
4. Do NOT modify tests/rules to pass

Common fixes:
- Import errors → Ensure cleanup modules properly imported
- Type errors → Add proper type hints to cleanup methods
- Test failures → Cleanup implementation doesn't match spec
```

## Usage Examples

### Scan Storage
```bash
# Just scan and show summary
python cleanup_experiments.py /scratch/users/jane/experiments --scan-only

# Output:
# Storage Summary for /scratch/users/jane/experiments
# ================================================================================
# Total experiments: 5
# Total jobs: 127
# Total size: 45.3 GB
#
# Experiment: resnet_sweep_v3
#   Path: /scratch/users/jane/experiments/resnet_sweep_v3
#   Total size: 23.1 GB
#   Jobs: 64
#   Storage breakdown:
#     - models: 20.5 GB
#     - metrics: 1.8 GB
#     - logs: 0.8 GB
#   Oldest file: 2024-01-15
#   Newest file: 2024-01-20
```

### Interactive Cleanup
```bash
# Interactive cleanup with confirmation
python cleanup_experiments.py /scratch/users/jane/experiments

# Dry run to see what would be deleted
python cleanup_experiments.py /scratch/users/jane/experiments --dry-run
```

### Automated Cleanup (Cron)
```bash
# Add to crontab for weekly cleanup of old experiments
0 2 * * 0 python /path/to/cleanup_experiments.py /scratch/users/jane/experiments --scan-only >> /path/to/cleanup.log 2>&1
```

## Final Validation Checklist

- [ ] **ALL quality checks pass**: `ckdr` shows "All checks passed!"
- [ ] **ALL tests pass**: `pt` shows all tests passing
- [ ] Test coverage is adequate: `pt --cov=dr_exp.tools`
- [ ] Cleanup tests pass: `pt tests/test_cleanup_tools.py -v`
- [ ] Storage scanner correctly identifies all experiments
- [ ] Size calculations are accurate
- [ ] Interactive cleaner shows correct options
- [ ] Dry-run mode doesn't delete anything
- [ ] Confirmation prompts work correctly
- [ ] Old experiment detection works (by date)
- [ ] Completed experiment detection works
- [ ] Pending sync warnings are shown

### Phase 6 Validation Gate

```bash
# No proceeding until these ALL work:
ckdr && echo "✓ Quality checks pass" || echo "✗ FIX CODE QUALITY FIRST"
pt tests/test_cleanup_tools.py && echo "✓ Cleanup tests pass" || echo "✗ FIX IMPLEMENTATION"
pt && echo "✓ All tests pass" || echo "✗ FIX ALL FAILURES"
```

If any check shows ✗:
1. STOP
2. Read the error carefully
3. Fix the implementation (not the test)
4. Run all checks again
5. Only proceed when all show ✓

## Common Test Anti-Patterns

### ⚠️ DO NOT Test Actual Deletions

❌ **WRONG - Don't delete real files in tests:**
```python
# This could delete important data!
cleaner = InteractiveCleaner("/real/path", dry_run=False)
cleaner.delete_experiment("important_exp")
```

✅ **RIGHT - Always use temp directories:**
```python
def test_deletion(tmp_path):
    cleaner = InteractiveCleaner(str(tmp_path), dry_run=False)
    # Safe to delete in tmp_path
```

### ⚠️ DO NOT Skip Dry-Run Testing

❌ **WRONG - Only testing actual operations:**
```python
def test_cleanup():
    cleaner.delete_old_experiments()  # Dangerous!
```

✅ **RIGHT - Test dry-run first:**
```python
def test_cleanup_dry_run():
    cleaner = InteractiveCleaner(path, dry_run=True)
    to_delete = cleaner.get_old_experiments()
    # Verify what would be deleted
```

## Architecture Notes

The cleanup tools are designed to be:
- **Safe by default**: Multiple confirmations, dry-run mode
- **Informative**: Clear breakdown of storage usage
- **Flexible**: Various cleanup strategies
- **Non-destructive**: Warns about pending syncs

## Next Steps

1. **Schedule regular scans**: Set up cron job to monitor storage growth
2. **Add remote cleanup**: Extend to clean Supabase storage too
3. **Archive option**: Instead of delete, archive to cheaper storage
4. **Storage quotas**: Add per-experiment storage limits

Congratulations! You now have a complete, clean experiment management system with proper storage management.