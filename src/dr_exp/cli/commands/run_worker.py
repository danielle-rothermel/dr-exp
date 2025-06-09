"""Run worker command."""

from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand


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
        assert args.worker_id.strip(), "Worker ID cannot be empty"
        assert args.work_dir.strip(), "Work directory cannot be empty"

        system = self.create_system()
        status = system.run_worker(worker_id=args.worker_id, work_dir=args.work_dir)
        
        # Provide helpful output based on status
        if status == "no_job_config_mismatch":
            print("Worker completed with status: no_job")
            print("⚠️  Configuration mismatch detected - see log output above for details")
            print("💡 Ensure DR_EXP_BASE_PATH is consistent between upload and worker commands")
        elif status == "no_job_db_error":
            print("Worker completed with status: no_job")
            print("❌ Database error occurred - check connection and configuration")
        elif status == "no_job":
            print("Worker completed with status: no_job")
            print("ℹ️  No jobs available - check log output above for diagnostics")
        else:
            print(f"Worker completed with status: {status}")

        # Set exit code based on status
        return 0 if status in ["completed", "success"] else 1
