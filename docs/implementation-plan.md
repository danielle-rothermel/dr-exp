# Implementation Plan: Updating dr_exp and deconCNN integration

## Agent Instructions
**IMPORTANT: Read these before starting implementation**

1. **Quality Gates**: Before EVERY commit:
   - Run `lint_fix` and resolve all issues
   - Run tests and ensure they pass
   - Fix any issues found, even if pre-existing

2. **Progress Tracking**:
   - Mark each step with ✅ when complete
   - Add notes in [brackets] for any deviations
   - Update the "Current Status" section after each work session

3. **Adaptation Protocol**:
   - Follow the plan but use judgment
   - Document any necessary modifications in [brackets]
   - Flag significant changes for retrospective

## Current Status
- Last updated: [timestamp]
- Last completed step: [none]
- Active agent: [agent name/session]
- Blocked by: [none]

## Implementation Steps

### Phase 1: dr_exp API Exposure
**Goal**: Expose JobDB as a public Python API

- [ ] **Step 1**: Create API module in dr_exp
  ```python
  # File: dr_exp/api/__init__.py (new file)
  """Public API for dr_exp."""
  from dr_exp.core.job_db import JobDB
  
  def submit_job(base_path, experiment, config, priority=100, tags=None):
      """Submit a job to dr_exp programmatically.
      
      Args:
          base_path: Base directory for experiments
          experiment: Experiment name
          config: Job configuration dict (must include _target_)
          priority: Job priority (0-1000)
          tags: Optional list of tags
          
      Returns:
          str: Job ID (UUID)
      """
      job_db = JobDB(base_path, experiment)
      return job_db.create_job(config, priority, tags)
  
  __all__ = ['submit_job', 'JobDB']
  ```
  **Testing**: 
  - Run `python -c "from dr_exp.api import submit_job; print(submit_job.__doc__)"`
  - Verify no import errors

- [ ] **Step 2**: Export API from package root
  ```python
  # File: dr_exp/__init__.py (modify existing)
  # Add at the end of file:
  from dr_exp.api import submit_job, JobDB
  ```
  **Testing**:
  - Run `python -c "from dr_exp import submit_job, JobDB; print('Success')"`
  - Run `pt` to ensure all tests pass

- [ ] **Step 3**: Add API test
  ```python
  # File: tests/test_api.py (new file)
  """Test public API functionality."""
  import pytest
  from pathlib import Path
  from dr_exp import submit_job, JobDB
  
  def test_submit_job_api(tmp_path):
      """Test programmatic job submission."""
      # Initialize experiment
      exp_path = tmp_path / "test_exp"
      JobDB.initialize_experiment(exp_path)
      
      # Submit job via API
      config = {
          "_target_": "os.path.exists",
          "path": "/tmp"
      }
      job_id = submit_job(
          base_path=tmp_path,
          experiment="test_exp",
          config=config,
          priority=150,
          tags=["api-test"]
      )
      
      # Verify job was created
      assert job_id is not None
      job_db = JobDB(tmp_path, "test_exp")
      job = job_db.get_job(job_id)
      assert job.config == config
      assert job.priority == 150
      assert "api-test" in job.tags
  ```
  **Testing**:
  - Run `pytest tests/test_api.py -v`
  - Run `pt` to ensure all tests pass

### Phase 2: deconCNN Integration Utilities
**Goal**: Add utilities for submitting jobs from deconCNN

- [ ] **Step 4**: Create dr_exp utilities module
  ```python
  # File: deconcnn/dr_exp_utils.py (new file)
  """Utilities for submitting deconCNN jobs to dr_exp."""
  from pathlib import Path
  from typing import Optional, List, Union
  from omegaconf import OmegaConf, DictConfig
  
  def submit_training_job(
      config_path: Union[str, Path],
      experiment: str = "decon_cnn",
      base_path: Union[str, Path] = "./experiments",
      priority: int = 100,
      tags: Optional[List[str]] = None,
      overrides: Optional[List[str]] = None
  ) -> str:
      """Submit a deconCNN training job to dr_exp.
      
      Args:
          config_path: Path to Hydra config file
          experiment: dr_exp experiment name
          base_path: Base path for experiments
          priority: Job priority (0-1000)
          tags: Optional job tags
          overrides: List of config overrides (e.g., ["model.name=resnet50"])
      
      Returns:
          job_id: UUID of submitted job
          
      Raises:
          ImportError: If dr_exp is not installed
          FileNotFoundError: If config file doesn't exist
      """
      # Validate config exists
      config_path = Path(config_path)
      if not config_path.exists():
          raise FileNotFoundError(f"Config not found: {config_path}")
      
      # Late import to make dr_exp optional dependency
      try:
          from dr_exp import submit_job
      except ImportError:
          raise ImportError(
              "dr_exp not installed. Install with: pip install dr_exp"
          )
      
      # Load config
      cfg = OmegaConf.load(config_path)
      
      # Apply overrides if provided
      if overrides:
          override_cfg = OmegaConf.from_dotlist(overrides)
          cfg = OmegaConf.merge(cfg, override_cfg)
      
      # Set target to existing decon_trainer
      cfg._target_ = "dr_exp.trainers.decon_trainer.train_classification"
      
      # Convert to dict for submission
      config_dict = OmegaConf.to_container(cfg, resolve=True)
      
      # Submit job
      return submit_job(
          base_path=str(base_path),
          experiment=experiment,
          config=config_dict,
          priority=priority,
          tags=tags
      )
  
  def list_decon_jobs(
      experiment: str = "decon_cnn",
      base_path: Union[str, Path] = "./experiments",
      status: Optional[str] = None
  ) -> List[dict]:
      """List deconCNN jobs in dr_exp.
      
      Args:
          experiment: Experiment name
          base_path: Base path for experiments
          status: Filter by status (queued/running/completed/failed)
          
      Returns:
          List of job summaries
      """
      try:
          from dr_exp import JobDB
      except ImportError:
          raise ImportError("dr_exp not installed")
      
      job_db = JobDB(str(base_path), experiment)
      jobs = job_db.list_jobs(status=status)
      
      # Filter to deconCNN jobs
      decon_jobs = []
      for job in jobs:
          if job.config.get('_target_', '').endswith('train_classification'):
              decon_jobs.append({
                  'id': job.id,
                  'status': job.status,
                  'priority': job.priority,
                  'created_at': job.created_at,
                  'tags': job.tags
              })
      
      return decon_jobs
  ```
  **Testing**:
  - Run `python -c "from deconcnn.dr_exp_utils import submit_training_job; print('Import success')"`
  - Check for syntax errors with `ruff check deconcnn/dr_exp_utils.py`

- [ ] **Step 5**: Add convenience script for batch submission
  ```python
  # File: deconcnn/scripts/submit_experiments.py (new file)
  #!/usr/bin/env python
  """Submit deconCNN experiments to dr_exp."""
  import click
  from pathlib import Path
  import itertools
  from typing import Optional
  from deconcnn.dr_exp_utils import submit_training_job, list_decon_jobs
  
  @click.group()
  def cli():
      """deconCNN experiment submission utilities."""
      pass
  
  @cli.command()
  @click.argument('config', type=Path)
  @click.option('--experiment', '-e', default='decon_cnn', help='Experiment name')
  @click.option('--base-path', '-b', default='./experiments', type=Path, help='Base path')
  @click.option('--priority', '-p', default=100, help='Job priority')
  @click.option('--tag', '-t', multiple=True, help='Job tags')
  @click.option('--override', '-o', multiple=True, help='Config overrides')
  def submit(config, experiment, base_path, priority, tag, override):
      """Submit a single training job."""
      try:
          job_id = submit_training_job(
              config_path=config,
              experiment=experiment,
              base_path=base_path,
              priority=priority,
              tags=list(tag) if tag else None,
              overrides=list(override) if override else None
          )
          click.echo(f"✅ Submitted job: {job_id}")
      except Exception as e:
          click.echo(f"❌ Error: {e}", err=True)
          raise click.Abort()
  
  @cli.command()
  @click.argument('config', type=Path)
  @click.option('--experiment', '-e', default='decon_cnn')
  @click.option('--base-path', '-b', default='./experiments', type=Path)
  @click.option('--priority', '-p', default=100)
  @click.option('--param', '-P', multiple=True, help='Sweep params (e.g., model.name=resnet18,resnet50)')
  @click.option('--dry-run', is_flag=True, help='Show what would be submitted')
  def sweep(config, experiment, base_path, priority, param, dry_run):
      """Submit parameter sweep."""
      if not param:
          click.echo("No sweep parameters provided. Use -P key=val1,val2", err=True)
          raise click.Abort()
      
      # Parse sweep parameters
      param_dict = {}
      for p in param:
          key, values = p.split('=')
          param_dict[key] = values.split(',')
      
      # Generate combinations
      keys = list(param_dict.keys())
      combinations = list(itertools.product(*[param_dict[k] for k in keys]))
      
      click.echo(f"Sweep will submit {len(combinations)} jobs:")
      
      for i, combo in enumerate(combinations):
          overrides = [f"{k}={v}" for k, v in zip(keys, combo)]
          click.echo(f"  [{i+1}] {', '.join(overrides)}")
          
          if not dry_run:
              job_id = submit_training_job(
                  config_path=config,
                  experiment=experiment,
                  base_path=base_path,
                  priority=priority,
                  overrides=overrides
              )
              click.echo(f"    → {job_id}")
      
      if dry_run:
          click.echo("\n(Dry run - no jobs submitted)")
  
  @cli.command()
  @click.option('--experiment', '-e', default='decon_cnn')
  @click.option('--base-path', '-b', default='./experiments', type=Path)
  @click.option('--status', '-s', type=click.Choice(['queued', 'running', 'completed', 'failed']))
  def list(experiment, base_path, status):
      """List deconCNN jobs."""
      try:
          jobs = list_decon_jobs(experiment, base_path, status)
          
          if not jobs:
              click.echo("No jobs found")
              return
          
          click.echo(f"Found {len(jobs)} jobs:")
          for job in jobs:
              status_emoji = {
                  'queued': '⏳',
                  'running': '🏃',
                  'completed': '✅',
                  'failed': '❌'
              }.get(job['status'], '❓')
              
              click.echo(f"{status_emoji} {job['id'][:8]} | Priority: {job['priority']} | {job['created_at']}")
              if job['tags']:
                  click.echo(f"   Tags: {', '.join(job['tags'])}")
                  
      except Exception as e:
          click.echo(f"Error: {e}", err=True)
  
  if __name__ == '__main__':
      cli()
  ```
  **Testing**:
  - Run `python deconcnn/scripts/submit_experiments.py --help`
  - Run `python deconcnn/scripts/submit_experiments.py submit --help`

### Phase 3: Integration Testing
**Goal**: Verify the integration works end-to-end

- [ ] **Step 6**: Add integration test in deconCNN
  ```python
  # File: tests/test_dr_exp_integration.py (new file)
  """Test dr_exp integration utilities."""
  import pytest
  from pathlib import Path
  from unittest.mock import patch, MagicMock
  from deconcnn.dr_exp_utils import submit_training_job, list_decon_jobs
  
  def test_submit_training_job_missing_config():
      """Test error when config file doesn't exist."""
      with pytest.raises(FileNotFoundError):
          submit_training_job("nonexistent.yaml")
  
  def test_submit_training_job_success(tmp_path):
      """Test successful job submission."""
      # Create test config
      config_file = tmp_path / "test.yaml"
      config_file.write_text("""
  model:
    name: resnet18
  optim:
    lr: 0.01
  """)
      
      # Mock dr_exp import and submit_job
      mock_submit = MagicMock(return_value="test-job-id")
      
      with patch.dict('sys.modules', {'dr_exp': MagicMock(submit_job=mock_submit)}):
          job_id = submit_training_job(
              config_path=config_file,
              experiment="test",
              priority=200,
              tags=["test-tag"],
              overrides=["model.name=resnet50"]
          )
          
          assert job_id == "test-job-id"
          
          # Verify submit_job was called correctly
          mock_submit.assert_called_once()
          call_args = mock_submit.call_args[1]
          assert call_args['experiment'] == "test"
          assert call_args['priority'] == 200
          assert call_args['tags'] == ["test-tag"]
          
          # Check config modifications
          config = call_args['config']
          assert config['_target_'] == "dr_exp.trainers.decon_trainer.train_classification"
          assert config['model']['name'] == "resnet50"  # Override applied
  
  def test_submit_without_dr_exp():
      """Test helpful error when dr_exp not installed."""
      with patch.dict('sys.modules', {'dr_exp': None}):
          with pytest.raises(ImportError, match="pip install dr_exp"):
              submit_training_job("dummy.yaml")
  ```
  **Testing**:
  - Run `pytest tests/test_dr_exp_integration.py -v`

### Phase 4: Documentation and Final Verification
**Goal**: Document usage and verify everything works

- [ ] **Step 7**: Update deconCNN documentation
  ```markdown
  # File: deconcnn/docs/dr_exp_usage.md (new file)
  # Using deconCNN with dr_exp
  
  ## Installation
  
  Install dr_exp alongside deconCNN:
  ```bash
  pip install dr_exp
  ```
  
  ## Submitting Jobs
  
  ### From Python
  ```python
  from deconcnn.dr_exp_utils import submit_training_job
  
  # Submit single job
  job_id = submit_training_job("configs/baseline.yaml")
  
  # Submit with overrides
  job_id = submit_training_job(
      "configs/baseline.yaml",
      overrides=["model.name=resnet50", "optim.lr=0.01"],
      priority=200,
      tags=["resnet50-experiment"]
  )
  ```
  
  ### From Command Line
  ```bash
  # Submit single job
  python -m deconcnn.scripts.submit_experiments submit configs/baseline.yaml
  
  # Submit with overrides
  python -m deconcnn.scripts.submit_experiments submit configs/baseline.yaml \
      -o model.name=resnet50 -o optim.lr=0.01 \
      -t baseline -t resnet50
  
  # Parameter sweep
  python -m deconcnn.scripts.submit_experiments sweep configs/baseline.yaml \
      -P model.name=resnet18,resnet50 \
      -P optim.lr=0.1,0.01,0.001
  
  # List jobs
  python -m deconcnn.scripts.submit_experiments list --status queued
  ```
  
  ## Running Workers
  
  After submitting jobs, run dr_exp workers as usual:
  ```bash
  dr_exp --base-path ./experiments --experiment decon_cnn worker --worker-id w1
  ```
  ```
  **Testing**: Visual review for completeness

- [ ] **Step 8**: End-to-end integration test
  ```bash
  # Create test script: test_integration.sh
  #!/bin/bash
  set -e
  
  echo "=== Testing dr_exp/deconCNN Integration ==="
  
  # 1. Test imports
  echo "1. Testing Python imports..."
  python -c "from dr_exp import submit_job; from deconcnn.dr_exp_utils import submit_training_job; print('✅ Imports successful')"
  
  # 2. Submit test job
  echo "2. Submitting test job..."
  python -c "
  from deconcnn.dr_exp_utils import submit_training_job
  job_id = submit_training_job('exp_configs/step00_baseline.yaml', experiment='integration_test')
  print(f'✅ Submitted job: {job_id}')
  "
  
  # 3. List jobs
  echo "3. Listing jobs..."
  python -m deconcnn.scripts.submit_experiments list -e integration_test
  
  echo "=== Integration test complete ==="
  ```
  **Testing**: 
  - Run `bash test_integration.sh`
  - Verify job appears in listing

## Handoff Instructions
To continue this implementation:
1. Read the full plan and agent instructions
2. Check "Current Status" to see where we are
3. Find the first unchecked [ ] item
4. Begin implementation from that point
5. Update status when stopping work

## Retrospective Notes
[Track significant decisions and deviations here]

---
Remember: Quality over speed. Test thoroughly. Document changes.