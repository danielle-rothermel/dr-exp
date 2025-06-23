#!/usr/bin/env python3
"""Submit all ablation experiments with 3 seeds each."""

import subprocess
from pathlib import Path

# Configuration
EXP_DIR = "/scratch/ddr8143/repos/dr_exp/chronological_ablation"
EXPERIMENT = "main"
SEEDS = [0, 1, 2]
CONFIG_PATH = "exp_configs"

# All step configs in order (higher priority for later steps to see results sooner)
STEPS = [
    "step00_baseline",
    "step01_sgd", 
    "step02_no_randaug",
    "step03_no_cutmix",
    "step04_no_mixup",
    "step05_no_warmup",
    "step06_steplr",
    "step07_no_residual",
    "step08_lrn_dropout",
    "step09_xavier",
    "step10_no_lrn",
    "step11_resnet12",
    "step12_alexnet",
    "step13_no_dropout",
    "step14_tanh",
    "step15_no_colorjitter",
    "step16_no_rrc",
    "step17_no_hflip",
]

def submit_job(config_name, seed, priority):
    """Submit a single job."""
    cmd = [
        "uv", "run", "dr_exp",
        "--base-path", EXP_DIR,
        "--experiment", EXPERIMENT,
        "job", "submit",
        "--config-path", CONFIG_PATH,
        "--config-name", f"{config_name}",
        "--overrides", f"seed={seed}",
        "--priority", str(priority)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        # Extract job ID from output
        for line in result.stdout.split('\n'):
            if line.startswith("Created job:"):
                job_id = line.split(": ")[1]
                return job_id
    else:
        print(f"Error submitting {config_name} seed={seed}: {result.stderr}")
        return None

# Submit all jobs
total_jobs = len(STEPS) * len(SEEDS)
job_count = 0

print(f"Submitting {total_jobs} jobs (18 experiments × 3 seeds)...")
print("=" * 60)

for step_idx, step_name in enumerate(STEPS):
    for seed_idx, seed in enumerate(SEEDS):
        # Priority: later steps get higher priority to see degradation sooner
        # Also prioritize seed 0 slightly to get one complete run per config faster
        # Scale to fit within 0-1000 range
        priority = (len(STEPS) - step_idx) * 50 + (2 - seed_idx) * 5
        priority = min(priority, 1000)  # Ensure within limits
        
        job_id = submit_job(step_name, seed, priority)
        job_count += 1
        
        if job_id:
            print(f"[{job_count:3d}/{total_jobs}] {step_name} seed={seed} priority={priority} -> {job_id}")
        else:
            print(f"[{job_count:3d}/{total_jobs}] {step_name} seed={seed} -> FAILED")

print("=" * 60)
print(f"Submitted {job_count} jobs to experiment: {EXPERIMENT}")
print(f"Base path: {EXP_DIR}")
print("\nTo monitor status:")
print(f"  uv run dr_exp --base-path {EXP_DIR} --experiment {EXPERIMENT} status")
print("\nTo launch workers (6 workers on 1 GPU):")
print(f"  uv run dr_exp --base-path {EXP_DIR} --experiment {EXPERIMENT} system launcher --workers-per-gpu 6")