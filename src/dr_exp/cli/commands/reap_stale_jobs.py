"""Reap stale jobs command."""

from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand
from dr_exp.utils.job_reaper import reap_stale_jobs
from dr_exp.utils.cli_config import CLI_DEFAULTS
from dr_exp.utils.cli_validation import validate_positive_int


class ReapStaleJobsCommand(BaseCommand):
    """Mark running jobs with stale heartbeats as failed."""
    
    @property
    def name(self) -> str:
        return "reap-stale-jobs"
    
    @property
    def help(self) -> str:
        return "Mark running jobs with stale heartbeats as failed"
    
    @property
    def description(self) -> str:
        return "Update stale running jobs to failed status"
    
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--max-age-mins",
            type=int,
            default=CLI_DEFAULTS.DEFAULT_MAX_AGE_MINS,
            help=f"Heartbeat age threshold in minutes (default: {CLI_DEFAULTS.DEFAULT_MAX_AGE_MINS})",
        )
    
    def run(self, args: Namespace) -> int:
        validate_positive_int(args.max_age_mins, "max-age-mins")
        
        system = self.create_system()
        client = system.job_db
        count = reap_stale_jobs(client, args.max_age_mins)
        print(f"Marked {count} stale job(s) as failed")
        
        return 0