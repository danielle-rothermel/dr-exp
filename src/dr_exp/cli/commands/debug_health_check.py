"""Debug health-check command to validate system state."""

import os
from argparse import ArgumentParser, Namespace
from typing import List, Tuple

from dr_exp.cli.base_command import BaseCommand
from dr_exp.job_db.config import JobDBConfig


class DebugHealthCheckCommand(BaseCommand):
    """Perform comprehensive system health check."""

    @property
    def name(self) -> str:
        return "debug-health-check"

    @property
    def help(self) -> str:
        return "Perform comprehensive system health check"

    @property
    def description(self) -> str:
        return "Validate configuration, check database connectivity, and verify system state"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--verbose", "-v", 
            action="store_true", 
            help="Show detailed information for all checks"
        )

    def run(self, args: Namespace) -> int:
        """Perform health check and report results."""
        print("🏥 System Health Check")
        print("=" * 50)
        
        checks: List[Tuple[str, bool, str]] = []
        overall_status = True
        
        try:
            system = self.create_system()
            config = JobDBConfig.from_env()
            job_db = system.job_db
            
            # Configuration validation
            print("\n📋 Configuration Checks:")
            try:
                config.validate()
                system.config.validate()
                checks.append(("Configuration validation", True, "All configuration values are valid"))
                print("  ✅ Configuration is valid")
            except Exception as e:
                checks.append(("Configuration validation", False, str(e)))
                print(f"  ❌ Configuration error: {e}")
                overall_status = False
            
            # Directory checks
            print("\n📁 Directory Checks:")
            jobs_dir = os.path.join(config.base_path, "job_data")
            
            # Jobs directory
            if os.path.exists(jobs_dir) and os.access(jobs_dir, os.R_OK | os.W_OK):
                checks.append(("Jobs directory", True, f"Exists and accessible: {jobs_dir}"))
                print(f"  ✅ Jobs directory accessible: {jobs_dir}")
            else:
                checks.append(("Jobs directory", False, f"Not accessible: {jobs_dir}"))
                print(f"  ❌ Jobs directory not accessible: {jobs_dir}")
                overall_status = False
            
            # Storage directory
            if os.path.exists(config.storage_path) and os.access(config.storage_path, os.R_OK | os.W_OK):
                checks.append(("Storage directory", True, f"Exists and accessible: {config.storage_path}"))
                print(f"  ✅ Storage directory accessible: {config.storage_path}")
            else:
                checks.append(("Storage directory", False, f"Not accessible: {config.storage_path}"))
                print(f"  ❌ Storage directory not accessible: {config.storage_path}")
                overall_status = False
            
            # Database connectivity
            print("\n🗄️  Database Checks:")
            try:
                # Test basic database operations
                has_queued = job_db.has_queued_jobs()
                running_jobs = job_db.list_running_jobs()
                checks.append(("Database connectivity", True, f"Successfully connected to {config.mode} database"))
                print(f"  ✅ Database connectivity ({config.mode})")
                
                if args.verbose:
                    print(f"    - Has queued jobs: {has_queued}")
                    print(f"    - Running jobs: {len(running_jobs)}")
                
            except Exception as e:
                checks.append(("Database connectivity", False, str(e)))
                print(f"  ❌ Database connection failed: {e}")
                overall_status = False
            
            # Job queue status
            print("\n📊 Job Queue Status:")
            try:
                queue_summary = job_db.get_queue_summary(limit=5)
                running_jobs = job_db.list_running_jobs()
                stale_jobs = job_db.get_stale_jobs(system.config.heartbeat_timeout * 2)
                
                print(f"  📋 Queued jobs: {len(queue_summary)}")
                print(f"  🏃 Running jobs: {len(running_jobs)}")
                print(f"  ⚠️  Stale jobs: {len(stale_jobs)}")
                
                if args.verbose and queue_summary:
                    print("  Top queued jobs:")
                    for job in queue_summary[:3]:
                        print(f"    - {job['id'][:8]}... Priority: {job['priority']}")
                
                if stale_jobs:
                    checks.append(("Stale jobs", False, f"Found {len(stale_jobs)} stale jobs"))
                    print(f"  ⚠️  Warning: {len(stale_jobs)} stale jobs found")
                    if args.verbose:
                        print("  Stale jobs:")
                        for job in stale_jobs[:3]:
                            print(f"    - {job.job_id[:8]}... Worker: {job.assigned_worker} Age: {job.age_seconds}s")
                else:
                    checks.append(("Stale jobs", True, "No stale jobs found"))
                
            except Exception as e:
                checks.append(("Job queue status", False, str(e)))
                print(f"  ❌ Error checking job status: {e}")
                overall_status = False
            
            # Worker capacity
            print("\n⚙️  Worker Capacity:")
            total_capacity = len(system.config.gpus) * system.config.workers_per_gpu
            print(f"  🎯 Total worker capacity: {total_capacity}")
            print(f"  🖥️  GPUs configured: {len(system.config.gpus)}")
            print(f"  👥 Workers per GPU: {system.config.workers_per_gpu}")
            
            if args.verbose:
                print(f"  GPU IDs: {system.config.gpus}")
            
            # Alternative job locations check (for files_local mode)
            if config.mode == "files_local":
                print("\n🔍 Alternative Location Check:")
                alternatives = self._check_alternative_locations(jobs_dir)
                if alternatives:
                    checks.append(("Alternative job locations", False, f"Found jobs in {len(alternatives)} other locations"))
                    print(f"  ⚠️  Found jobs in alternative locations:")
                    for alt in alternatives:
                        print(f"    - {alt}")
                    print("  💡 This may indicate configuration inconsistencies")
                else:
                    checks.append(("Alternative job locations", True, "No jobs found in alternative locations"))
                    print("  ✅ No alternative job locations found")
            
            # Summary
            print("\n📋 Health Check Summary:")
            print("=" * 30)
            
            passed_checks = sum(1 for _, status, _ in checks if status)
            total_checks = len(checks)
            
            for check_name, status, details in checks:
                status_icon = "✅" if status else "❌"
                print(f"  {status_icon} {check_name}")
                if args.verbose or not status:
                    print(f"    {details}")
            
            print(f"\n📊 Overall: {passed_checks}/{total_checks} checks passed")
            
            if overall_status:
                print("🎉 System is healthy!")
                return 0
            else:
                print("⚠️  System has issues that need attention")
                return 1
                
        except Exception as e:
            print(f"❌ Health check failed with error: {e}")
            return 1

    def _check_alternative_locations(self, current_jobs_dir: str) -> List[str]:
        """Check for job files in alternative locations."""
        alternatives = []
        common_paths = ["./job_data", "./logs/job_data", "../job_data", "job_data"]
        
        for alt_path in common_paths:
            if alt_path != current_jobs_dir and os.path.exists(alt_path):
                try:
                    job_files = [f for f in os.listdir(alt_path) if f.endswith('.json')]
                    if job_files:
                        alternatives.append(f"{alt_path} ({len(job_files)} jobs)")
                except (OSError, PermissionError):
                    continue
        
        return alternatives