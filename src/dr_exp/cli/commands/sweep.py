"""Sweep command for parameter exploration."""

import click
from dr_exp.cli.sweep_utils import (
    parse_sweep_params,
    generate_sweep_configs,
    validate_sweep_config,
)


@click.command()
@click.option("--config", required=True, help="Base Hydra config file")
@click.option(
    "--params",
    required=True,
    help='Sweep parameters (e.g., "model=r18,r50 lr=0.01,0.001")',
)
@click.option("--priority", default=100, type=int, help="Job priority (0-1000)")
@click.option("--target", help="Override _target_ in config")
@click.option("--dry-run", is_flag=True, help="Show configs without creating jobs")
@click.option("--verbose", is_flag=True, help="Show detailed config information")
@click.pass_context
def sweep(  # noqa: C901
    ctx: click.Context,
    config: str,
    params: str,
    priority: int,
    target: str,
    dry_run: bool,
    verbose: bool,
) -> None:
    r"""Submit a parameter sweep based on a config file.

    Examples:
        # Basic sweep
        dr_exp --base-path /scratch --experiment exp1 job sweep \\
            --config configs/train.yaml \\
            --params "model=resnet18,resnet50 lr=0.001,0.01"

        # With target override
        dr_exp --base-path /scratch --experiment exp1 job sweep \\
            --config configs/base.yaml \\
            --params "epochs=10,20,50" \\
            --target dr_exp.training.train_model

        # Dry run to preview
        dr_exp --base-path /scratch --experiment exp1 job sweep \\
            --config configs/train.yaml \\
            --params "batch_size=32,64,128 lr=0.001,0.01" \\
            --dry-run
    """
    # Create JobDB instance for this command
    from dr_exp.core.job_db import JobDB

    job_db = JobDB(
        base_path=ctx.obj["base_path"], experiment_name=ctx.obj["experiment"]
    )

    # Parse sweep parameters
    sweep_params = parse_sweep_params(params)

    if not sweep_params:
        click.echo("Error: No valid parameters found in sweep string", err=True)
        ctx.exit(1)

    # Show what we're sweeping
    click.echo("Sweep parameters:")
    for key, values in sweep_params.items():
        click.echo(f"  {key}: {values}")

    # Generate all configs
    try:
        configs = generate_sweep_configs(config, sweep_params)
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        ctx.exit(1)

    click.echo(f"\nGenerating {len(configs)} configurations")

    # Apply target override if provided
    if target:
        for cfg in configs:
            cfg["_target_"] = target

    if dry_run:
        # Show configurations without creating jobs
        for i, cfg in enumerate(configs):
            click.echo(f"\n--- Config {i + 1}/{len(configs)} ---")
            if verbose:
                # Show full config
                import json

                click.echo(json.dumps(cfg, indent=2))
            else:
                # Show only the swept parameters and target
                click.echo(f"_target_: {cfg.get('_target_', 'NOT SET')}")
                for key in sweep_params:
                    # Navigate nested keys
                    value = cfg
                    for part in key.split("."):
                        if isinstance(value, dict):
                            value = value.get(part, "NOT FOUND")
                        else:
                            value = "NOT FOUND"
                            break
                    click.echo(f"{key}: {value}")
        return

    # Create all jobs
    created = 0
    failed = 0

    for i, cfg in enumerate(configs):
        try:
            # Validate config
            validate_sweep_config(cfg)

            # Create job
            job_db.create_job(cfg, priority)
            created += 1

            # Show progress for large sweeps
            PROGRESS_THRESHOLD = 20
            if len(configs) > PROGRESS_THRESHOLD and (i + 1) % 10 == 0:
                click.echo(f"Progress: {i + 1}/{len(configs)} jobs...")

        except Exception as e:
            failed += 1
            if verbose:
                click.echo(f"Error creating job {i + 1}: {e}", err=True)

    # Summary
    click.echo("\nSweep complete:")
    click.echo(f"  Created: {created} jobs")
    if failed > 0:
        click.echo(f"  Failed: {failed} jobs", err=True)
    click.echo(f"  Priority: {priority}")
