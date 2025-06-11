#!/usr/bin/env python3
"""Create wrapper configs with _target_ for all step configs."""

from pathlib import Path

# Template for wrapper configs
WRAPPER_TEMPLATE = """_target_: "dr_exp.trainers.decon_trainer.train_classification"
defaults:
  - ../{base_config}
  - _self_

# Full training for sweep
epochs: 200
batch_size: 128
"""

exp_configs_dir = Path("/scratch/ddr8143/repos/dr_exp/exp_configs")
wrapper_dir = exp_configs_dir / "dr_exp_wrappers"
wrapper_dir.mkdir(exist_ok=True)

# Find all step configs
step_configs = sorted(exp_configs_dir.glob("step*.yaml"))

for config_path in step_configs:
    # Create wrapper config
    wrapper_name = config_path.stem + "_wrapper"
    wrapper_path = wrapper_dir / f"{wrapper_name}.yaml"
    
    content = WRAPPER_TEMPLATE.format(base_config=config_path.stem)
    wrapper_path.write_text(content)
    print(f"Created {wrapper_path}")

print(f"\nCreated {len(step_configs)} wrapper configs in {wrapper_dir}")