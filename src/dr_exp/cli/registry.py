"""Command registry for CLI commands."""

from typing import Dict, Type

from dr_exp.cli.base_command import BaseCommand
from dr_exp.cli.commands.run import RunCommand
from dr_exp.cli.commands.discover_gpus import DiscoverGpusCommand
from dr_exp.cli.commands.run_worker import RunWorkerCommand
from dr_exp.cli.commands.list_jobs import ListJobsCommand
from dr_exp.cli.commands.boost_priority import BoostPriorityCommand
from dr_exp.cli.commands.set_priority import SetPriorityCommand
from dr_exp.cli.commands.run_one import RunOneCommand
from dr_exp.cli.commands.reap_stale_jobs import ReapStaleJobsCommand
from dr_exp.cli.commands.cleanup_run_data import CleanupRunDataCommand
from dr_exp.cli.commands.upload_configs import UploadConfigsCommand


class CommandRegistry:
    """Registry for managing CLI commands."""
    
    def __init__(self):
        self._commands: Dict[str, Type[BaseCommand]] = {}
        self._register_default_commands()
    
    def _register_default_commands(self) -> None:
        """Register all default commands."""
        commands = [
            RunCommand,
            DiscoverGpusCommand,
            RunWorkerCommand,
            ListJobsCommand,
            BoostPriorityCommand,
            SetPriorityCommand,
            RunOneCommand,
            ReapStaleJobsCommand,
            CleanupRunDataCommand,
            UploadConfigsCommand,
        ]
        
        for command_class in commands:
            self.register(command_class)
    
    def register(self, command_class: Type[BaseCommand]) -> None:
        """Register a command class.
        
        Parameters
        ----------
        command_class : Type[BaseCommand]
            Command class to register
        """
        # Create temporary instance to get the name
        instance = command_class()
        self._commands[instance.name] = command_class
    
    def get(self, name: str) -> Type[BaseCommand]:
        """Get a command class by name.
        
        Parameters
        ----------
        name : str
            Command name
            
        Returns
        -------
        Type[BaseCommand]
            Command class
            
        Raises
        ------
        KeyError
            If command is not found
        """
        if name not in self._commands:
            raise KeyError(f"Unknown command: {name}")
        return self._commands[name]
    
    def list_commands(self) -> Dict[str, str]:
        """List all available commands with their help text.
        
        Returns
        -------
        Dict[str, str]
            Mapping of command names to help text
        """
        result = {}
        for name, command_class in self._commands.items():
            instance = command_class()
            result[name] = instance.help
        return result
    
    @property
    def command_names(self) -> list[str]:
        """Get list of all command names."""
        return list(self._commands.keys())


# Global registry instance
COMMAND_REGISTRY = CommandRegistry()