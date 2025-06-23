#!/usr/bin/env python3
"""Utilities for safe job submission with proper error handling and duplicate detection."""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class SubmissionLogger:
    """Logs all submission attempts to a JSON file for recovery/auditing."""

    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.submissions: List[Dict[str, Any]] = []

        # Load existing log if present
        if log_file.exists():
            with open(log_file) as f:
                data = json.load(f)
                self.submissions = data.get("submissions", [])

    def log_submission(
        self,
        config: str,
        seed: int,
        job_id: str,
        success: bool,
        error: Optional[str] = None,
    ):
        """Log a submission attempt."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "config": config,
            "seed": seed,
            "job_id": job_id,
            "success": success,
            "error": error,
        }
        self.submissions.append(entry)
        self._save()

    def _save(self):
        """Save log to disk."""
        with open(self.log_file, "w") as f:
            json.dump({"submissions": self.submissions}, f, indent=2)

    def get_successful_submissions(self) -> Set[Tuple[str, int]]:
        """Return set of (config, seed) tuples for successful submissions."""
        return {
            (s["config"], s["seed"])
            for s in self.submissions
            if s["success"] and s["job_id"]
        }


class JobSubmitter:
    """Handles job submission with safety features."""

    def __init__(self, base_path: Path, experiment: str, dry_run: bool = False):
        self.base_path = base_path
        self.experiment = experiment
        self.dry_run = dry_run
        self.failed_jobs: List[Dict[str, Any]] = []

        # Set up logging
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = base_path / experiment / "submission_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.logger = SubmissionLogger(log_dir / f"submission_{timestamp}.json")

    def check_existing_jobs(self) -> Set[Tuple[str, int]]:
        """Check for existing jobs to avoid duplicates."""
        try:
            result = subprocess.run(
                [
                    "dr_exp",
                    "--base-path",
                    str(self.base_path),
                    "--experiment",
                    self.experiment,
                    "job",
                    "list",
                    "--status",
                    "all",
                ],
                capture_output=True,
                text=True,
            )

            existing = set()
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    # Parse job info to extract config and seed
                    # This is still somewhat fragile but better than before
                    if "config:" in line and "seed:" in line:
                        try:
                            # Extract config name
                            config_start = line.find("config:") + 7
                            config_end = line.find(" ", config_start)
                            if config_end == -1:
                                config_end = line.find(",", config_start)
                            config = line[config_start:config_end].strip()

                            # Extract seed
                            seed_start = line.find("seed:") + 5
                            seed_end = line.find(" ", seed_start)
                            if seed_end == -1:
                                seed_end = line.find(",", seed_start)
                            seed = int(line[seed_start:seed_end].strip())

                            existing.add((config, seed))
                        except:
                            # Skip malformed lines
                            pass

            return existing
        except Exception as e:
            print(f"Warning: Could not check existing jobs: {e}")
            return set()

    def validate_config(self, config_path: str) -> bool:
        """Validate that config file exists."""
        # Handle both relative and absolute paths
        paths_to_check = [
            Path(config_path),
            self.base_path / config_path,
            self.base_path / self.experiment / config_path,
            Path.cwd() / config_path,
        ]

        for path in paths_to_check:
            if path.exists():
                return True

        return False

    def submit_job(
        self,
        config: str,
        seed: int,
        priority: int = 0,
        extra_overrides: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Submit a single job. Returns (success, job_id)."""

        if self.dry_run:
            print(
                f"[DRY RUN] Would submit: config={config}, seed={seed}, priority={priority}"
            )
            return True, "dry-run-job-id"

        # Build overrides string
        overrides = [f"seed={seed}"]
        if extra_overrides:
            overrides.append(extra_overrides)

        cmd = [
            "dr_exp",
            "--base-path",
            str(self.base_path),
            "--experiment",
            self.experiment,
            "job",
            "submit",
            "--config-path",
            "exp_configs",
            "--config-name",
            config,
            "--overrides",
            ",".join(overrides),
        ]

        if priority > 0:
            cmd.extend(["--priority", str(priority)])

        if tags:
            cmd.extend(["--tags", ",".join(tags)])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                # Extract job ID from output
                job_id = None
                for line in result.stdout.strip().split("\n"):
                    if "Job submitted with ID:" in line:
                        job_id = line.split(":")[-1].strip()
                        break

                self.logger.log_submission(config, seed, job_id or "unknown", True)
                return True, job_id
            else:
                error = result.stderr.strip() or "Unknown error"
                self.logger.log_submission(config, seed, "", False, error)
                self.failed_jobs.append(
                    {"config": config, "seed": seed, "error": error}
                )
                return False, None

        except Exception as e:
            error = str(e)
            self.logger.log_submission(config, seed, "", False, error)
            self.failed_jobs.append({"config": config, "seed": seed, "error": error})
            return False, None

    def print_summary(self):
        """Print submission summary with failure details."""
        if self.failed_jobs:
            print("\n❌ FAILED SUBMISSIONS:")
            print("=" * 60)
            for job in self.failed_jobs:
                print(f"Config: {job['config']}, Seed: {job['seed']}")
                print(f"Error: {job['error']}")
                print("-" * 40)

            # Generate rerun command
            failed_configs = sorted(
                set((j["config"], j["seed"]) for j in self.failed_jobs)
            )
            print("\n📝 To retry failed jobs, run:")
            print("python submit_jobs.py --only-failed", end="")
            for config, seed in failed_configs[:3]:  # Show first 3 as example
                print(f" --job {config},{seed}", end="")
            if len(failed_configs) > 3:
                print(f" ... ({len(failed_configs) - 3} more)")
            else:
                print()

            print(f"\nOr check the log file: {self.logger.log_file}")
        else:
            print("\n✅ All submissions successful!")
            print(f"Log file: {self.logger.log_file}")
