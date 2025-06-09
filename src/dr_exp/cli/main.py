"""Main CLI module using command pattern architecture."""

import sys
from argparse import ArgumentParser
from typing import Sequence, Optional

from dotenv import load_dotenv

from dr_exp.cli.registry import COMMAND_REGISTRY
from dr_exp.cli.command_groups import COMMAND_GROUP_MAPPING, CommandGroupRegistry

load_dotenv()


def build_parser() -> ArgumentParser:
    """Build the main CLI argument parser with grouped commands."""
    parser = ArgumentParser(
        description="Experiment manager command line interface", prog="manager-cli"
    )

    subparsers = parser.add_subparsers(
        dest="group", required=True, help="Command groups"
    )

    # Create group registry
    group_registry = CommandGroupRegistry()

    # Add grouped subcommands
    for group_name, command_names in COMMAND_GROUP_MAPPING.items():
        group = group_registry.get_group(group_name)

        # Create subparser for this group
        group_parser = subparsers.add_parser(
            group_name, help=group.help, description=group.description
        )

        # Add subcommands for this group
        group_subparsers = group_parser.add_subparsers(
            dest="command", required=True, help=f"Available {group_name} commands"
        )

        for command_name in command_names:
            command_class = COMMAND_REGISTRY.get(command_name)
            command_instance = command_class()

            # Create subparser for this command
            command_parser = group_subparsers.add_parser(
                command_instance.name.replace(
                    "-", "_"
                ),  # Use underscores for subcommands
                help=command_instance.help,
                description=command_instance.description,
            )

            # Let the command add its arguments
            command_instance.add_arguments(command_parser)

    return parser


def _find_command_name_in_group(group_name: str, command_attr: str) -> str:
    """Find the original command name from the group and command attribute."""
    if group_name in COMMAND_GROUP_MAPPING:
        # Convert underscores back to hyphens and find matching command
        command_with_hyphens = command_attr.replace("_", "-")
        for cmd_name in COMMAND_GROUP_MAPPING[group_name]:
            if cmd_name == command_with_hyphens:
                return cmd_name
    assert False, f"Command not found: {command_attr} in group {group_name}"


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
        # Find the actual command name from the group structure
        command_name = _find_command_name_in_group(args.group, args.command)

        # Get the command class and create an instance
        command_class = COMMAND_REGISTRY.get(command_name)
        command = command_class()

        # Execute the command
        return command.execute(args)

    except KeyError:
        print(
            f"Unknown command: {getattr(args, 'command', 'unknown')} in group {getattr(args, 'group', 'unknown')}",
            file=sys.stderr,
        )
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
