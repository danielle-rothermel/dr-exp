"""Clean up run data command."""

from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand
from dr_exp.utils.storage_cleanup import cleanup_uploaded_runs


class CleanupRunDataCommand(BaseCommand):
    """Delete run directories that have finished uploading."""
    
    @property
    def name(self) -> str:
        return "cleanup-run-data"
    
    @property
    def help(self) -> str:
        return "Delete run directories that have finished uploading"
    
    @property
    def description(self) -> str:
        return "Remove run_* folders containing finished.flag"
    
    def add_arguments(self, parser: ArgumentParser) -> None:
        # No additional arguments needed
        pass
    
    def run(self, args: Namespace) -> int:
        system = self.create_system()
        client = system.job_db
        count = cleanup_uploaded_runs(client)
        print(f"Removed {count} run directory(s)")
        
        return 0