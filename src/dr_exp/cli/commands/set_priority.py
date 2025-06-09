"""Set priority command."""

from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand
from dr_exp.utils.cli_validation import validate_job_id, validate_priority


class SetPriorityCommand(BaseCommand):
    """Set the priority of a specific job."""

    @property
    def name(self) -> str:
        return "set-priority"

    @property
    def help(self) -> str:
        return "Set the priority of a specific job"

    @property
    def description(self) -> str:
        return "Set job priority to exact value"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("job_id", help="Job ID to update")
        parser.add_argument("priority", type=int, help="New priority value (0-1000)")
        parser.add_argument(
            "--reason",
            help="Optional reason for priority change",
        )

    def run(self, args: Namespace) -> int:
        validate_job_id(args.job_id)
        validate_priority(args.priority)

        system = self.create_system()
        client = system.job_db
        result = client.update_job_priority(
            args.job_id, args.priority, reason=args.reason
        )

        if result["success"]:
            print(f"Priority updated to {args.priority}")
            if args.reason:
                print(f"Reason: {args.reason}")
            return 0
        else:
            print(
                f"Failed to update priority: {result['message']}"
            )
            return 1
