"""Run manager command."""

from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand
from dr_exp.utils.factory import SystemConfig
from dr_exp.utils.gpu_discovery import discover_gpus
from dr_exp.utils.cli_config import CLI_DEFAULTS
from dr_exp.utils.cli_validation import validate_positive_int


class RunCommand(BaseCommand):
    """Start the manager process."""
    
    @property
    def name(self) -> str:
        return "run"
    
    @property
    def help(self) -> str:
        return "Start the manager process"
    
    @property
    def description(self) -> str:
        return "Launch the manager which supervises worker processes"
    
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--gpus-per-node",
            type=int,
            default=CLI_DEFAULTS.GPUS_PER_NODE,
            help=f"Number of GPUs available on this node (default: {CLI_DEFAULTS.GPUS_PER_NODE})",
        )
        parser.add_argument(
            "--workers-per-gpu",
            type=int,
            default=CLI_DEFAULTS.WORKERS_PER_GPU,
            help=f"Number of worker processes to spawn per GPU (default: {CLI_DEFAULTS.WORKERS_PER_GPU})",
        )
        parser.add_argument(
            "--heartbeat-timeout",
            type=int,
            default=CLI_DEFAULTS.HEARTBEAT_TIMEOUT,
            help=f"Worker heartbeat timeout in seconds (default: {CLI_DEFAULTS.HEARTBEAT_TIMEOUT})",
        )
        parser.add_argument(
            "--idle-timeout-mins",
            type=int,
            default=CLI_DEFAULTS.IDLE_TIMEOUT_MINS,
            help=f"Minutes of inactivity before the manager shuts down (default: {CLI_DEFAULTS.IDLE_TIMEOUT_MINS})",
        )
    
    def run(self, args: Namespace) -> int:
        # Validate inputs
        validate_positive_int(args.gpus_per_node, "gpus-per-node")
        validate_positive_int(args.workers_per_gpu, "workers-per-gpu")
        validate_positive_int(args.heartbeat_timeout, "heartbeat-timeout")
        validate_positive_int(args.idle_timeout_mins, "idle-timeout-mins")
        
        # Discover GPUs
        gpus = discover_gpus(args.gpus_per_node)
        
        # Create system configuration
        system_config = SystemConfig(
            gpus=gpus,
            workers_per_gpu=args.workers_per_gpu,
            heartbeat_timeout=args.heartbeat_timeout,
            idle_timeout_mins=args.idle_timeout_mins,
        )
        
        # Create and run manager
        system = self.create_system(system_config)
        manager = system.create_manager()
        manager.run()
        
        return 0