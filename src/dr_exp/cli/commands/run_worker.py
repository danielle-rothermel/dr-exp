"""Run worker command."""

from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand
from dr_exp.utils.cli_validation import ValidationError


class RunWorkerCommand(BaseCommand):
    """Run a single worker process."""
    
    @property
    def name(self) -> str:
        return "run-worker"
    
    @property
    def help(self) -> str:
        return "Run a single worker process"
    
    @property
    def description(self) -> str:
        return "Execute a worker directly using run_worker_main"
    
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("worker_id", help="Unique worker identifier")
        parser.add_argument("work_dir", help="Working directory for temporary files")
    
    def run(self, args: Namespace) -> int:
        # Basic validation
        if not args.worker_id.strip():
            raise ValidationError("Worker ID cannot be empty")
        if not args.work_dir.strip():
            raise ValidationError("Work directory cannot be empty")
            
        system = self.create_system()
        status = system.run_worker(
            worker_id=args.worker_id,
            work_dir=args.work_dir
        )
        print(f"Worker completed with status: {status}")
        
        # Set exit code based on status
        return 0 if status in ["completed", "success"] else 1