"""Command line interface for the experiment manager.

This module provides backward compatibility by delegating to the new
command pattern architecture in dr_exp.cli.
"""

import sys
from typing import Sequence

from dr_exp.cli.main import main as cli_main


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point for the CLI.

    This function maintains backward compatibility while delegating
    to the new command pattern architecture.
    """
    exit_code = cli_main(argv)
    sys.exit(exit_code)


def build_arg_parser():
    """Deprecated: Use dr_exp.cli.main.build_parser instead."""
    from dr_exp.cli.main import build_parser

    return build_parser()


if __name__ == "__main__":
    main()


__all__ = ["main", "build_arg_parser"]
