"""Command group definitions for organizing CLI commands."""

from typing import Dict, List, Type
from dr_exp.cli.base_command import BaseCommand


class CommandGroup:
    """Represents a group of related commands."""
    
    def __init__(self, name: str, help: str, description: str):
        self.name = name
        self.help = help
        self.description = description
        self.commands: List[Type[BaseCommand]] = []
    
    def add_command(self, command_class: Type[BaseCommand]) -> None:
        """Add a command to this group."""
        self.commands.append(command_class)


class CommandGroupRegistry:
    """Registry for managing command groups."""
    
    def __init__(self):
        self.groups: Dict[str, CommandGroup] = {}
        self._setup_default_groups()
    
    def _setup_default_groups(self) -> None:
        """Set up the default command groups."""
        # System commands: managing the experiment system
        self.add_group(CommandGroup(
            name="system",
            help="System management commands",
            description="Commands for managing the experiment system and infrastructure"
        ))
        
        # Job commands: working with individual jobs
        self.add_group(CommandGroup(
            name="job",
            help="Job management commands", 
            description="Commands for managing individual experiment jobs"
        ))
        
        # Admin commands: administrative operations
        self.add_group(CommandGroup(
            name="admin",
            help="Administrative commands",
            description="Administrative commands for system maintenance"
        ))
    
    def add_group(self, group: CommandGroup) -> None:
        """Add a command group."""
        self.groups[group.name] = group
    
    def get_group(self, name: str) -> CommandGroup:
        """Get a command group by name."""
        return self.groups[name]
    
    def list_groups(self) -> Dict[str, str]:
        """List all groups with their help text."""
        return {name: group.help for name, group in self.groups.items()}


# Define command-to-group mappings
COMMAND_GROUP_MAPPING = {
    # System commands
    "system": [
        "run",
        "discover-gpus", 
        "run-worker",
        "status"
    ],
    
    # Job commands  
    "job": [
        "list-jobs",
        "boost-priority",
        "set-priority", 
        "run-one",
        "upload-configs"
    ],
    
    # Admin commands
    "admin": [
        "reap-stale-jobs",
        "cleanup-run-data"
    ]
}