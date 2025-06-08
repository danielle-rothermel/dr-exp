"""Base command class for CLI commands."""

import sys
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from typing import Optional

from dr_exp.utils.factory import create_system, SystemConfig, Factory
from dr_exp.utils.cli_validation import ValidationError


class BaseCommand(ABC):
    """Abstract base class for CLI commands."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Command name."""
        pass

    @property
    @abstractmethod
    def help(self) -> str:
        """Short help text for the command."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Detailed description for the command."""
        pass

    @abstractmethod
    def add_arguments(self, parser: ArgumentParser) -> None:
        """Add command-specific arguments to the parser.

        Parameters
        ----------
        parser : ArgumentParser
            The argument parser to add arguments to
        """
        pass

    @abstractmethod
    def run(self, args: Namespace) -> int:
        """Execute the command.

        Parameters
        ----------
        args : Namespace
            Parsed command line arguments

        Returns
        -------
        int
            Exit code (0 for success, non-zero for failure)
        """
        pass

    def create_system(self, system_config: Optional[SystemConfig] = None) -> Factory:
        """Create a system factory with optional configuration.

        Parameters
        ----------
        system_config : SystemConfig, optional
            System configuration. If None, uses defaults from environment.

        Returns
        -------
        Factory
            System factory instance
        """
        return create_system(system_config)

    def handle_error(self, error: Exception, message: str = None) -> int:
        """Handle command errors consistently.

        Parameters
        ----------
        error : Exception
            The error that occurred
        message : str, optional
            Custom error message prefix

        Returns
        -------
        int
            Exit code (always 1 for errors)
        """
        if isinstance(error, ValidationError):
            print(f"Error: {error}", file=sys.stderr)
        elif message:
            print(f"{message}: {error}", file=sys.stderr)
        else:
            print(f"Command failed: {error}", file=sys.stderr)

        return 1

    def execute(self, args: Namespace) -> int:
        """Execute the command with error handling.

        This is the main entry point that wraps run() with consistent error handling.

        Parameters
        ----------
        args : Namespace
            Parsed command line arguments

        Returns
        -------
        int
            Exit code
        """
        try:
            return self.run(args)
        except ValidationError as e:
            return self.handle_error(e)
        except Exception as e:
            return self.handle_error(e)
