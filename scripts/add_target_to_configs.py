#!/usr/bin/env python3
"""Add _target_ to all step configs."""

from pathlib import Path

# Target to add
TARGET_LINE = '_target_: "dr_exp.trainers.decon_trainer.train_classification"\n'

# Find all step configs
exp_configs_dir = Path("/scratch/ddr8143/repos/dr_exp/exp_configs")
step_configs = sorted(exp_configs_dir.glob("step*.yaml"))

for config_path in step_configs:
    # Read current content
    content = config_path.read_text()
    
    # Check if target already exists
    if '_target_' not in content:
        # Add target as first line
        new_content = TARGET_LINE + content
        config_path.write_text(new_content)
        print(f"Added _target_ to {config_path.name}")
    else:
        print(f"Skipping {config_path.name} - already has _target_")

print(f"\nProcessed {len(step_configs)} configs")