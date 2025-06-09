"""System status command."""

from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand


class StatusCommand(BaseCommand):
    """Show system status and environment information."""

    @property
    def name(self) -> str:
        return "status"

    @property
    def help(self) -> str:
        return "Show system status and environment information"

    @property
    def description(self) -> str:
        return (
            "Display current system configuration, job status, and environment details"
        )

    def add_arguments(self, parser: ArgumentParser) -> None:
        self.add_common_arguments(parser)

    def run(self, args: Namespace) -> int:
        system = self.create_system_from_args(args)
        status = system.get_system_status()

        print("=== System Status ===")

        # Configuration
        config = status["configuration"]
        print(f"Mode: {config['mode']}")
        print(f"GPUs: {config['gpus']}")
        print(f"Workers per GPU: {config['workers_per_gpu']}")
        print(f"Total capacity: {config['total_worker_capacity']} workers")
        print(f"Heartbeat timeout: {config['heartbeat_timeout']}s")
        print(f"Manager directory: {config['manager_base_dir']}")

        # Environment
        env = status["environment"]
        print("\n=== Environment ===")
        print(f"Scheduler: {env['scheduler']}")
        if env["job_id"]:
            print(f"Job ID: {env['job_id']}")
        print(f"Node: {env['node_name']}")
        print(f"Process ID: {env['process_id']}")
        if env["cuda_visible_devices"]:
            print(f"CUDA_VISIBLE_DEVICES: {env['cuda_visible_devices']}")

        # Job status
        job_status = status["job_status"]
        print("\n=== Job Status ===")
        print(f"Running jobs: {job_status['running_jobs']}")
        print(f"Queued jobs: {'Yes' if job_status['has_queued_jobs'] else 'No'}")
        print(f"Stale jobs: {job_status['stale_jobs']}")

        # Queue preview
        if status["queue_preview"]:
            print("\n=== Top Queued Jobs ===")
            for job in status["queue_preview"]:
                print(f"  {job['id']}: priority {job['priority']}")

        # Stale jobs preview
        if status["stale_jobs_preview"]:
            print("\n=== Stale Jobs ===")
            for job in status["stale_jobs_preview"]:
                print(
                    f"  {job['job_id']}: worker {job['worker']}, {job['age_seconds']}s old"
                )

        return 0
