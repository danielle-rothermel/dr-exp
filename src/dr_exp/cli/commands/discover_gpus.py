"""Discover GPUs command."""

from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand
from dr_exp.utils.gpu_discovery import discover_gpus
from dr_exp.utils.cli_config import CLI_DEFAULTS
from dr_exp.utils.cli_validation import validate_positive_int


class DiscoverGpusCommand(BaseCommand):
    """List visible GPU IDs."""

    @property
    def name(self) -> str:
        return "discover-gpus"

    @property
    def help(self) -> str:
        return "List visible GPU IDs"

    @property
    def description(self) -> str:
        return "Print GPU IDs that the manager would use"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--gpus-per-node",
            type=int,
            default=CLI_DEFAULTS.GPUS_PER_NODE,
            help=f"Total GPUs on the node if CUDA_VISIBLE_DEVICES is not set (default: {CLI_DEFAULTS.GPUS_PER_NODE})",
        )

    def run(self, args: Namespace) -> int:
        validate_positive_int(args.gpus_per_node, "gpus-per-node")
        gpus = discover_gpus(args.gpus_per_node)
        for gpu in gpus:
            print(gpu)
        return 0
