# Fix Hydra Config Composition

## Objective
Replace YAML loading in submit command with Hydra's compose API to support config composition.

## Files to Modify
- `/src/dr_exp/cli/main.py` - Replace yaml.safe_load with Hydra compose

## Implementation

### Step 1: Update submit command in cli/main.py

Find the submit function (around line 78) and replace it entirely:

```python
@click.command()
@click.option("--config-path", default="configs", help="Path to config directory")
@click.option("--config-name", required=True, help="Name of config file (without .yaml)")
@click.option("--priority", default=100, help="Job priority (0-1000)")
@click.option("--tag", help="Job tag")
@click.option("--overrides", help="Hydra overrides (key=value,key2=value2)")
@click.pass_context
def submit(
    ctx: click.Context,
    config_path: str,
    config_name: str,
    priority: int,
    tag: Optional[str],
    overrides: Optional[str],
) -> None:
    """Submit a job using Hydra config composition."""
    from hydra import compose, initialize_config_dir
    from hydra.core.global_hydra import GlobalHydra
    from omegaconf import OmegaConf
    import os
    
    # Clear any existing Hydra instance
    GlobalHydra.instance().clear()
    
    # Convert config path to absolute
    if not os.path.isabs(config_path):
        config_path = os.path.abspath(config_path)
    
    # Prepare overrides list
    override_list = []
    if overrides:
        override_list = [o.strip() for o in overrides.split(",")]
    
    try:
        # Initialize Hydra with config path
        with initialize_config_dir(config_dir=config_path, version_base="1.3"):
            # Compose configuration
            cfg = compose(config_name=config_name, overrides=override_list)
            
            # Convert to plain dict for storage
            config_dict = OmegaConf.to_container(cfg, resolve=True)
    except Exception as e:
        click.echo(f"Error composing config: {e}", err=True)
        ctx.exit(1)
    
    # Validate _target_ exists
    if "_target_" not in config_dict:
        click.echo("Error: Config must contain '_target_' field", err=True)
        ctx.exit(1)
    
    # Validate target is importable
    target = config_dict["_target_"]
    module_path = target.rsplit(".", 1)[0]
    try:
        importlib.import_module(module_path)
    except ImportError as e:
        click.echo(f"Error: Cannot import target module {module_path}: {e}", err=True)
        ctx.exit(1)
    
    # Create job
    job_db = ctx.obj["job_db"]
    job_id = job_db.create_job(
        config=config_dict,
        priority=priority,
        tag=tag,
    )
    
    click.echo(f"Created job: {job_id}")
    click.echo(f"Priority: {priority}")
    click.echo(f"Target: {target}")
```

### Step 2: Update CLI help text

In the same file, update the main CLI group docstring (around line 558):

```python
@click.group()
@click.option("--base-path", required=True, help="Base path for experiments")
@click.option("--experiment", required=True, help="Experiment name")
@click.pass_context
def cli(ctx: click.Context, base_path: str, experiment: str) -> None:
    """dr_exp - ML experiment manager.
    
    Example:
        dr_exp --base-path ./experiments --experiment my_exp submit --config-name train
    """
```

### Step 3: Add Hydra imports at top of file

Add these imports after the existing imports:

```python
import importlib
from typing import Optional
```

### Step 4: Remove old submit command implementation

Remove the old submit command and its file loading logic completely.

## Test

Create test file `/tests/implementation/test_hydra_fix.py`:

```python
import pytest
from pathlib import Path
import yaml
from click.testing import CliRunner
from dr_exp.cli.main import cli

def test_hydra_config_composition(tmp_path):
    # Create config structure
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    
    # Create base config with composition
    base_config = {
        "defaults": ["model"],
        "_target_": "dr_exp.trainers.test_trainer.train",
        "epochs": 10
    }
    (config_dir / "train.yaml").write_text(yaml.dump(base_config))
    
    # Create model config
    model_config = {"layers": 3, "hidden_size": 128}
    (config_dir / "model.yaml").write_text(yaml.dump(model_config))
    
    # Create experiment
    exp_path = tmp_path / "experiment"
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--base-path", str(tmp_path),
        "--experiment", "experiment",
        "init"
    ])
    assert result.exit_code == 0
    
    # Submit with composition
    result = runner.invoke(cli, [
        "--base-path", str(tmp_path),
        "--experiment", "experiment",
        "submit",
        "--config-path", str(config_dir),
        "--config-name", "train"
    ])
    assert result.exit_code == 0
    assert "Created job:" in result.output
    
    # Verify composed config
    job_files = list((exp_path / "jobs").glob("*.json"))
    assert len(job_files) == 1
    
    import json
    job_data = json.loads(job_files[0].read_text())
    assert job_data["config"]["layers"] == 3  # From composed model.yaml
    assert job_data["config"]["epochs"] == 10  # From train.yaml

def test_overrides(tmp_path):
    # Create simple config
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    
    config = {
        "_target_": "dr_exp.trainers.test_trainer.train",
        "epochs": 10,
        "lr": 0.01
    }
    (config_dir / "train.yaml").write_text(yaml.dump(config))
    
    # Create experiment
    runner = CliRunner()
    runner.invoke(cli, [
        "--base-path", str(tmp_path),
        "--experiment", "experiment",
        "init"
    ])
    
    # Submit with overrides
    result = runner.invoke(cli, [
        "--base-path", str(tmp_path),
        "--experiment", "experiment",
        "submit",
        "--config-path", str(config_dir),
        "--config-name", "train",
        "--overrides", "epochs=20,lr=0.001"
    ])
    assert result.exit_code == 0
    
    # Verify overrides applied
    exp_path = tmp_path / "experiment"
    job_files = list((exp_path / "jobs").glob("*.json"))
    
    import json
    job_data = json.loads(job_files[0].read_text())
    assert job_data["config"]["epochs"] == 20
    assert job_data["config"]["lr"] == 0.001
```

## Verification Steps

1. Run tests: `pt tests/implementation/test_hydra_fix.py -v`
2. Test with real DeconCNN config:
   ```bash
   dr_exp --base-path ./test --experiment hydra_test init
   dr_exp --base-path ./test --experiment hydra_test submit --config-path configs --config-name decon_config
   ```
3. Verify job created with fully composed config

## Common Mistakes to Avoid
- DO NOT keep yaml.safe_load code
- DO NOT support old file path syntax
- DO NOT allow missing _target_ field
- DO NOT catch exceptions during composition - let them fail fast