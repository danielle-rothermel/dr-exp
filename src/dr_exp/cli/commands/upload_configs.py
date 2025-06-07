"""Upload configs command."""

from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand
from scripts import upload_configs


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
        upload_configs.add_arguments(parser)
    
    def run(self, args: Namespace) -> int:
        jobs = upload_configs.run(args)
        print(f"Created {len(jobs)} job(s)")
        return 0