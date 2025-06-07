"""List jobs command."""

from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand
from dr_exp.utils.cli_config import CLI_DEFAULTS
from dr_exp.utils.cli_validation import validate_job_statuses, validate_positive_int


class ListJobsCommand(BaseCommand):
    """List jobs ordered by priority."""
    
    @property
    def name(self) -> str:
        return "list-jobs"
    
    @property
    def help(self) -> str:
        return "List jobs ordered by priority"
    
    @property
    def description(self) -> str:
        return "Display jobs in priority order with status filtering"
    
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--status",
            nargs="*",
            default=CLI_DEFAULTS.DEFAULT_JOB_STATUS,
            help=f"Filter by job status (default: {CLI_DEFAULTS.DEFAULT_JOB_STATUS})",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=CLI_DEFAULTS.DEFAULT_JOB_LIMIT,
            help=f"Maximum number of jobs to display (default: {CLI_DEFAULTS.DEFAULT_JOB_LIMIT})",
        )
    
    def run(self, args: Namespace) -> int:
        validate_job_statuses(args.status)
        validate_positive_int(args.limit, "limit")
        
        system = self.create_system()
        client = system.job_db
        jobs = client.list_jobs_by_priority(status_filter=args.status, limit=args.limit)
        
        if not jobs:
            print("No jobs found matching criteria")
            return 0
        
        print(f"{'Job ID':<40} {'Priority':<8} {'Status':<10} {'Created':<20}")
        print("-" * 80)
        for job in jobs:
            job_id = str(job.get("id", ""))[:36]
            priority = job.get("priority", 100)
            status = job.get("status", "unknown")
            created = job.get("created_at", "")[:19] if job.get("created_at") else ""
            print(f"{job_id:<40} {priority:<8} {status:<10} {created:<20}")
        
        return 0