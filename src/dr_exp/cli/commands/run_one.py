"""Run one job command."""

from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand
from dr_exp.utils.cli_config import CLI_DEFAULTS
from dr_exp.utils.cli_validation import validate_priority, validate_config_overrides
from dr_exp.utils.run_one_config import create_run_one_job, get_default_config_path


class RunOneCommand(BaseCommand):
    """Reserve and run a single high-priority job immediately."""

    @property
    def name(self) -> str:
        return "run-one"

    @property
    def help(self) -> str:
        return "Reserve and run a single high-priority job immediately"

    @property
    def description(self) -> str:
        return "Create a reserved high-priority job and execute it immediately"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--overrides",
            default="",
            help="Hydra-style config overrides (e.g., 'model=resnet,lr=0.001')",
        )
        parser.add_argument(
            "--priority",
            type=int,
            default=CLI_DEFAULTS.RUN_ONE_PRIORITY,
            help=f"Job priority (default: {CLI_DEFAULTS.RUN_ONE_PRIORITY})",
        )
        parser.add_argument(
            "--config-path",
            default=get_default_config_path(),
            help="Path to config directory (default: auto-detected)",
        )
        parser.add_argument(
            "--config-name",
            default="config.yaml",
            help="Config file name (default: config.yaml)",
        )

    def run(self, args: Namespace) -> int:
        validate_priority(args.priority)
        overrides = validate_config_overrides(args.overrides)

        system = self.create_system()
        client = system.job_db

        # Create job using proper config generation
        job = create_run_one_job(
            client=client,
            base_config_path=args.config_path,
            config_name=args.config_name,
            overrides=overrides,
            priority=args.priority,
        )
        print(f"Created job {job['id']} with priority {args.priority}")

        # Run worker targeting this specific job
        status = system.run_worker(worker_id="run_one_worker", target_job_id=job["id"])
        print(f"Job completed with status: {status}")

        # Return appropriate exit code
        return 0 if status in ["completed", "success"] else 1
