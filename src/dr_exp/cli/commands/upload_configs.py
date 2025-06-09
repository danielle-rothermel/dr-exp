"""Upload configs command."""

from argparse import ArgumentParser, Namespace
from pathlib import Path

from dr_exp.cli.base_command import BaseCommand
from dr_exp.utils import config_upload
from dr_exp.utils.jobdb_factory import get_job_db_client


class UploadConfigsCommand(BaseCommand):
    """Generate and upload sweep configs."""

    @property
    def name(self) -> str:
        return "upload-configs"

    @property
    def help(self) -> str:
        return "Generate and upload sweep configs"

    @property
    def description(self) -> str:
        return "Generate configs and upload them using the database"

    def add_arguments(self, parser: ArgumentParser) -> None:
        # Get the project root directory (2 levels up from this file)
        project_root = Path(__file__).resolve().parents[4]
        default_config_path = str(project_root / "configs")

        parser.add_argument(
            "--base-config-path",
            default=default_config_path,
            help="Directory containing Hydra config files",
        )
        parser.add_argument(
            "--config-name",
            default="config.yaml",
            help="Name of the main config file (e.g. config.yaml)",
        )
        parser.add_argument("--sweep", default="", help="Sweep definition")
        parser.add_argument("--cluster-name")
        parser.add_argument("--description")
        parser.add_argument("--interface-version")
        parser.add_argument("--code-version")
        parser.add_argument(
            "--priority",
            type=int,
            default=100,
            help="Job priority (0-1000, higher = more urgent). Default: 100",
        )

    def run(self, args: Namespace) -> int:
        client = get_job_db_client()

        # Convert relative path to absolute path for Hydra
        base_config_path = Path(args.base_config_path).resolve()

        jobs = config_upload.upload_configs(
            base_config_path=str(base_config_path),
            config_name=args.config_name,
            sweep=args.sweep,
            client=client,
            cluster_name=args.cluster_name,
            description=args.description,
            interface_version=args.interface_version,
            code_version=args.code_version,
            priority=args.priority,
        )
        print(f"Created {len(jobs)} job(s)")
        return 0
