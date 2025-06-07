"""Main CLI module using command pattern architecture."""

import sys
from argparse import ArgumentParser
from typing import Sequence, Optional

from dotenv import load_dotenv

from dr_exp.cli.registry import COMMAND_REGISTRY

load_dotenv()


def build_parser() -> ArgumentParser:
    """Build the main CLI argument parser."""
    parser = ArgumentParser(
        description="Experiment manager command line interface",
        prog="manager-cli"
    )
    
    subparsers = parser.add_subparsers(
        dest="command", 
        required=True,
        help="Available commands"
    )
    
    # Add all registered commands
    for command_name in COMMAND_REGISTRY.command_names:
        command_class = COMMAND_REGISTRY.get(command_name)
        command_instance = command_class()
        
        # Create subparser for this command
        command_parser = subparsers.add_parser(
            command_instance.name,
            help=command_instance.help,
            description=command_instance.description
        )
        
        # Let the command add its arguments
        command_instance.add_arguments(command_parser)
    
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main CLI entry point.
    
    Parameters
    ----------
    argv : Optional[Sequence[str]]
        Command line arguments. If None, uses sys.argv.
        
    Returns
    -------
    int
        Exit code
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    
    try:
        # Get the command class and create an instance
        command_class = COMMAND_REGISTRY.get(args.command)
        command = command_class()
        
        # Execute the command
        return command.execute(args)
        
    except KeyError as e:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        parser.print_help()
        return 1
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())