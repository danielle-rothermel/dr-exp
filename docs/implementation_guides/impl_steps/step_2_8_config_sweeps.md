# Step 2.8: Config Sweeps

## Goal (1 sentence)
Add parameter sweep functionality to generate and submit multiple job configurations from a single command.

## Prerequisites
- [ ] Step 2.7 completed and validated
- [ ] CLI framework with job submission working
- [ ] Hydra configs being used for job configuration
- [ ] JobDB can create jobs with configs

## Implementation

### 1. Create src/dr_exp/cli/sweep_utils.py
```python
"""Utilities for parameter sweeps."""
import itertools
from pathlib import Path
from typing import List, Dict, Any
import hydra
from hydra.core.global_hydra import GlobalHydra
from omegaconf import OmegaConf


def parse_sweep_params(params_str: str) -> Dict[str, List[str]]:
    """Parse sweep parameters from string format.
    
    Example: "model=resnet18,resnet50 optim.lr=0.001,0.01"
    Returns: {"model": ["resnet18", "resnet50"], "optim.lr": ["0.001", "0.01"]}
    
    Args:
        params_str: String containing sweep parameters
        
    Returns:
        Dictionary mapping parameter names to lists of values
    """
    if not params_str:
        return {}
    
    result = {}
    # Split by whitespace to get individual param=values pairs
    pairs = params_str.split()
    for pair in pairs:
        if '=' not in pair:
            continue
        key, values = pair.split('=', 1)
        result[key] = [v.strip() for v in values.split(',')]
    return result


def generate_sweep_configs(
    base_config: str,
    sweep_params: Dict[str, List[str]]
) -> List[Dict[str, Any]]:
    """Generate all config combinations for a parameter sweep.
    
    Args:
        base_config: Path to base Hydra config file
        sweep_params: Parameters to sweep over
        
    Returns:
        List of composed configs
    """
    if not sweep_params:
        # No sweep, just load base config
        return [load_hydra_config(base_config, [])]
    
    # Generate all combinations
    keys = list(sweep_params.keys())
    values = [sweep_params[k] for k in keys]
    
    configs = []
    for combo in itertools.product(*values):
        overrides = [f"{k}={v}" for k, v in zip(keys, combo)]
        config = load_hydra_config(base_config, overrides)
        configs.append(config)
    
    return configs


def load_hydra_config(config_path: str, overrides: List[str]) -> Dict[str, Any]:
    """Load and compose a Hydra config with overrides.
    
    Args:
        config_path: Path to config file
        overrides: List of override strings (e.g., ["model=resnet50", "lr=0.01"])
        
    Returns:
        Composed config as dictionary
    """
    config_path = Path(config_path).resolve()
    config_dir = config_path.parent
    config_name = config_path.name
    
    # Clear any existing Hydra state
    GlobalHydra.instance().clear()
    
    # Initialize and compose
    with hydra.initialize_config_dir(config_dir=str(config_dir), version_base=None):
        cfg = hydra.compose(config_name=config_name, overrides=overrides)
        # Convert to regular dict and resolve
        return OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)


def validate_sweep_config(config: Dict[str, Any]) -> None:
    """Validate that a config is ready for job submission.
    
    Args:
        config: Config dictionary to validate
        
    Raises:
        AssertionError: If config is invalid
    """
    assert isinstance(config, dict), "Config must be a dictionary"
    assert "_target_" in config, "Config must include _target_ field"
    
    # Validate target is importable
    target = config["_target_"]
    try:
        module_path, func_name = target.rsplit('.', 1)
        import importlib
        module = importlib.import_module(module_path)
        assert hasattr(module, func_name), f"Function {func_name} not found in {module_path}"
    except Exception as e:
        assert False, f"Cannot import target {target}: {e}"
```

### 2. Add sweep command to CLI (create src/dr_exp/cli/commands/sweep.py)
```python
"""Sweep command for parameter exploration."""
import click
from dr_exp.cli.sweep_utils import (
    parse_sweep_params, 
    generate_sweep_configs,
    validate_sweep_config
)


@click.command()
@click.option('--config', required=True, help='Base Hydra config file')
@click.option('--params', required=True, help='Sweep parameters (e.g., "model=r18,r50 lr=0.01,0.001")')
@click.option('--priority', default=100, type=int, help='Job priority (0-1000)')
@click.option('--target', help='Override _target_ in config')
@click.option('--dry-run', is_flag=True, help='Show configs without creating jobs')
@click.option('--verbose', is_flag=True, help='Show detailed config information')
@click.pass_context
def sweep(ctx, config: str, params: str, priority: int, target: str, dry_run: bool, verbose: bool):
    """Submit a parameter sweep based on a config file.
    
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
    job_db = ctx.obj['job_db']
    
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
            cfg['_target_'] = target
    
    if dry_run:
        # Show configurations without creating jobs
        for i, cfg in enumerate(configs):
            click.echo(f"\n--- Config {i+1}/{len(configs)} ---")
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
                    for part in key.split('.'):
                        if isinstance(value, dict):
                            value = value.get(part, 'NOT FOUND')
                        else:
                            value = 'NOT FOUND'
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
            job_id = job_db.create_job(cfg, priority)
            created += 1
            
            # Show progress for large sweeps
            if len(configs) > 20 and (i + 1) % 10 == 0:
                click.echo(f"Progress: {i + 1}/{len(configs)} jobs...")
                
        except Exception as e:
            failed += 1
            if verbose:
                click.echo(f"Error creating job {i+1}: {e}", err=True)
    
    # Summary
    click.echo(f"\nSweep complete:")
    click.echo(f"  Created: {created} jobs")
    if failed > 0:
        click.echo(f"  Failed: {failed} jobs", err=True)
    click.echo(f"  Priority: {priority}")
```

### 3. Create test configs for testing (test_configs/sweep_test.yaml)
```yaml
# Test config for parameter sweeps
_target_: dr_exp.training.dummy_trainer.train_dummy

# Model config
model:
  name: resnet18
  num_classes: 10

# Training config  
epochs: 10
batch_size: 32
lr: 0.001

# Data config
data:
  dataset: cifar10
  augment: true
```

### 4. Create tests/implementation/test_step_2_8.py
```python
"""Test config sweep functionality."""
import tempfile
import json
import pytest
from pathlib import Path
from click.testing import CliRunner

from src.dr_exp.core.job_db import JobDB
from src.dr_exp.cli.sweep_utils import (
    parse_sweep_params,
    generate_sweep_configs,
    validate_sweep_config
)
from src.dr_exp.cli.main import cli


def test_parse_sweep_params():
    """Test parsing sweep parameter strings."""
    # Basic parsing
    params = parse_sweep_params("model=resnet18,resnet50 lr=0.001,0.01")
    assert params == {
        "model": ["resnet18", "resnet50"],
        "lr": ["0.001", "0.01"]
    }
    
    # Nested parameters
    params = parse_sweep_params("optim.lr=0.1,0.01 model.layers=12,24")
    assert params == {
        "optim.lr": ["0.1", "0.01"],
        "model.layers": ["12", "24"]
    }
    
    # Single values
    params = parse_sweep_params("epochs=100")
    assert params == {"epochs": ["100"]}
    
    # Empty string
    params = parse_sweep_params("")
    assert params == {}
    
    # Invalid format (no equals)
    params = parse_sweep_params("invalid_param another_invalid")
    assert params == {}
    


def test_generate_configs():
    """Test config generation from sweeps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test config
        config_dir = Path(tmpdir) / "configs"
        config_dir.mkdir()
        
        config_file = config_dir / "test.yaml"
        config_file.write_text("""
_target_: dr_exp.training.dummy_trainer.train_dummy
model: resnet18
lr: 0.001
epochs: 10
""")
        
        # Generate configs
        sweep_params = {"model": ["resnet18", "resnet50"], "lr": ["0.001", "0.01"]}
        configs = generate_sweep_configs(str(config_file), sweep_params)
        
        # Should have 2x2=4 configs
        assert len(configs) == 4
        
        # Check all combinations exist
        combinations = []
        for cfg in configs:
            combinations.append((cfg["model"], cfg["lr"]))
        
        assert ("resnet18", 0.001) in combinations
        assert ("resnet18", 0.01) in combinations
        assert ("resnet50", 0.001) in combinations
        assert ("resnet50", 0.01) in combinations
        
        # All should have the target
        for cfg in configs:
            assert cfg["_target_"] == "dr_exp.training.dummy_trainer.train_dummy"
        


def test_validate_config():
    """Test config validation."""
    # Valid config
    config = {
        "_target_": "dr_exp.training.dummy_trainer.train_dummy",
        "epochs": 10
    }
    validate_sweep_config(config)  # Should not raise
    
    # Missing target
    try:
        validate_sweep_config({"epochs": 10})
        assert False, "Should have failed"
    except AssertionError as e:
        assert "_target_" in str(e)
    
    # Invalid target
    try:
        validate_sweep_config({"_target_": "nonexistent.module.func"})
        assert False, "Should have failed"
    except AssertionError as e:
        assert "Cannot import" in str(e)
    


def test_sweep_cli_dry_run():
    """Test sweep CLI command in dry-run mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        # Create test config
        config_file = Path(tmpdir) / "test.yaml"
        config_file.write_text("""
_target_: dr_exp.training.dummy_trainer.train_dummy
model: resnet18
lr: 0.001
epochs: 10
""")
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'job', 'sweep',
            '--config', str(config_file),
            '--params', 'model=resnet18,resnet50 lr=0.001,0.01',
            '--dry-run'
        ])
        
        assert result.exit_code == 0
        assert "Generating 4 configurations" in result.output
        assert "Config 1/4" in result.output
        assert "Config 4/4" in result.output
        assert "resnet18" in result.output
        assert "resnet50" in result.output
        
        # No jobs should be created
        jobs = job_db.list_jobs()
        assert len(jobs) == 0
        


def test_sweep_cli_create_jobs():
    """Test sweep CLI command creating actual jobs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        # Create test config
        config_file = Path(tmpdir) / "test.yaml"
        config_file.write_text("""
_target_: dr_exp.training.dummy_trainer.train_dummy
epochs: 10
batch_size: 32
""")
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'job', 'sweep',
            '--config', str(config_file),
            '--params', 'epochs=10,20,30',
            '--priority', '500'
        ])
        
        assert result.exit_code == 0
        assert "Created: 3 jobs" in result.output
        
        # Check jobs were created
        jobs = job_db.list_jobs()
        assert len(jobs) == 3
        
        # Check each job has correct config
        epochs_values = [job["config"]["epochs"] for job in jobs]
        assert sorted(epochs_values) == [10, 20, 30]
        
        # All should have priority 500
        for job in jobs:
            assert job["priority"] == 500
        


def test_sweep_with_target_override():
    """Test sweep with target override."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        # Config without _target_
        config_file = Path(tmpdir) / "base.yaml"
        config_file.write_text("""
model: resnet18
lr: 0.001
""")
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'job', 'sweep',
            '--config', str(config_file),
            '--params', 'lr=0.1,0.01',
            '--target', 'dr_exp.training.dummy_trainer.train_dummy',
            '--priority', '300'
        ])
        
        assert result.exit_code == 0
        assert "Created: 2 jobs" in result.output
        
        # Check jobs have the target
        jobs = job_db.list_jobs()
        assert len(jobs) == 2
        for job in jobs:
            assert job["config"]["_target_"] == "dr_exp.training.dummy_trainer.train_dummy"
        


def test_large_sweep_progress():
    """Test progress reporting for large sweeps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        config_file = Path(tmpdir) / "test.yaml"
        config_file.write_text("""
_target_: dr_exp.training.dummy_trainer.train_dummy
model: resnet18
""")
        
        # Create a large sweep (3x3x3 = 27 jobs)
        runner = CliRunner()
        result = runner.invoke(cli, [
            '--base-path', tmpdir,
            '--experiment', 'test_exp',
            'job', 'sweep',
            '--config', str(config_file),
            '--params', 'lr=0.1,0.01,0.001 batch_size=16,32,64 epochs=10,20,30'
        ])
        
        assert result.exit_code == 0
        assert "Generating 27 configurations" in result.output
        assert "Progress:" in result.output  # Should show progress
        assert "Created: 27 jobs" in result.output
        


```

## Validation
```bash
# Install required dependencies
uv add hydra-core omegaconf

# Run the test with pytest
pt tests/implementation/test_step_2_8.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_2_8.py::test_parse_sweep_params PASSED
# tests/implementation/test_step_2_8.py::test_generate_configs PASSED
# tests/implementation/test_step_2_8.py::test_validate_config PASSED
# tests/implementation/test_step_2_8.py::test_sweep_cli_dry_run PASSED
# tests/implementation/test_step_2_8.py::test_sweep_cli_create_jobs PASSED
# tests/implementation/test_step_2_8.py::test_sweep_with_target_override PASSED
# tests/implementation/test_step_2_8.py::test_large_sweep_progress PASSED
# ============================== 7 passed in X.XXs ===============================

# Verify code quality (runs ruff linting/formatting + mypy type checks)
ckdr

# Expected: All checks passed!

# Add sweep command to CLI
# Update src/dr_exp/cli/command_groups.py to include:
# from .commands.sweep import sweep
# job_group.add_command(sweep)
```

## Common Mistakes
- DO NOT: Try to evaluate sweep parameters as Python code - parse them as strings
- DO NOT: Load all configs into memory at once for huge sweeps
- DO NOT: Forget to validate _target_ exists and is importable
- DO NOT: Use complex parameter formats - keep it simple with key=val1,val2
- DO NOT: Modify the base config file - use Hydra overrides

## Next Step
Proceed to Step 2.9: SLURM Integration