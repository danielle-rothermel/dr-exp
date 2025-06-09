"""Boost priority command."""

from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand
from dr_exp.utils.cli_config import CLI_DEFAULTS
from dr_exp.utils.cli_validation import validate_job_id, validate_positive_int


class BoostPriorityCommand(BaseCommand):
    """Boost the priority of a specific job."""

    @property
    def name(self) -> str:
        return "boost-priority"

    @property
    def help(self) -> str:
        return "Boost the priority of a specific job"

    @property
    def description(self) -> str:
        return "Increase job priority by specified amount"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("job_id", help="Job ID to boost")
        parser.add_argument(
            "--amount",
            type=int,
            default=CLI_DEFAULTS.PRIORITY_BOOST_AMOUNT,
            help=f"Priority boost amount (default: {CLI_DEFAULTS.PRIORITY_BOOST_AMOUNT})",
        )

    def run(self, args: Namespace) -> int:
        validate_job_id(args.job_id)
        validate_positive_int(args.amount, "amount")

        system = self.create_system()
        client = system.job_db
        result = client.boost_job_priority(args.job_id, boost_amount=args.amount)

        if result.get("success"):
            print(
                f"Priority boosted: {result['old_priority']} -> {result['new_priority']}"
            )
            return 0
        else:
            print(f"Failed to boost priority: {result.get('message', 'Unknown error')}")
            return 1
