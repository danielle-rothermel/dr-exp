#!/usr/bin/env python3
"""Send control commands to running launchers."""

import click
from pathlib import Path


@click.command()
@click.argument("command", type=click.Choice(["stop", "finish-current", "status"]))
@click.option("--base-path", required=True, help="Base experiment path")
@click.option("--experiment", required=True, help="Experiment name")
@click.option("--job-id", help="SLURM job ID (defaults to all)")
def main(
    command: str, base_path: str, experiment: str, job_id: str | None = None
) -> None:
    """Send control commands to launcher."""
    control_dir = Path(base_path) / experiment / "control"

    if command == "status":
        # Show status files
        for status_file in control_dir.glob("status_*.json"):
            print(f"\nStatus from {status_file.name}:")
            print(status_file.read_text())
    else:
        # Create control file
        if job_id:
            targets = [job_id]
        else:
            # Find all active launchers
            targets = []
            for status_file in control_dir.glob("status_*.json"):
                job_id = status_file.stem.replace("status_", "")
                targets.append(job_id)

        if not targets:
            print("No active launchers found")
            return

        for target in targets:
            if command == "stop":
                control_file = control_dir / f"stop_{target}"
            elif command == "finish-current":
                control_file = control_dir / f"finish_current_{target}"

            control_file.touch()
            print(f"Sent {command} to launcher {target}")


if __name__ == "__main__":
    main()
