# dr_exp Project Workflows

This document covers project-specific workflows for job submission, monitoring, and management using the dr_exp system.

## Job Submission Workflows

### Unified Submission Script

The primary submission tool is `scripts/submission/submit_jobs.py`, which provides safety features and handles multiple experiment types.

#### Basic Usage

```bash
# Navigate to project root
cd /path/to/your/project

# Preview what would be submitted (always do this first!)
./scripts/submission/submit_jobs.py --experiment-type chrono --dry-run

# Submit chronological experiments
./scripts/submission/submit_jobs.py --experiment-type chrono

# Submit high-regularization experiments  
./scripts/submission/submit_jobs.py --experiment-type high-reg

# Submit both experiment types
./scripts/submission/submit_jobs.py --experiment-type both
```

#### Safety Features

**🛡️ Built-in Protections:**
- **Dry Run Mode** (`--dry-run`) - Preview submissions without executing
- **Duplicate Detection** (`--skip-existing`) - Prevents accidental resubmissions (default: enabled)
- **Transaction Logging** - All submissions logged to `submission_logs/`
- **Config Validation** - Validates all config files exist before submitting
- **Clear Error Reporting** - Shows exactly what failed and why

**📝 Transaction Logs:**
```bash
# Check submission history
ls submission_logs/
cat submission_logs/submission_20240115_143022.json
```

#### Advanced Usage

```bash
# Submit specific configs with default seeds
./scripts/submission/submit_jobs.py --configs step00_baseline step01_sgd

# Submit with custom seeds
./scripts/submission/submit_jobs.py --configs step00_baseline --seeds 0 1 2

# Submit with custom priority (higher = runs first)
./scripts/submission/submit_jobs.py --configs step00_baseline --priority 200

# Retry failed jobs from last run
./scripts/submission/submit_jobs.py --retry-failed

# Force resubmit (ignores existing jobs)
./scripts/submission/submit_jobs.py --experiment-type chrono --force

# Skip confirmation prompts (for automation)
./scripts/submission/submit_jobs.py --experiment-type chrono --no-confirm
```

### Experiment Types

The submission script supports predefined experiment configurations:

**Chronological Experiments** (`--experiment-type chrono`):
- step00_baseline.yaml through step17_no_hflip.yaml
- Priorities: 170 (baseline) down to 0 (no_hflip)
- Default seeds: 0, 1, 2

**High-Regularization Experiments** (`--experiment-type high-reg`):
- step00_baseline_high_reg.yaml through step04_no_mixup_high_reg.yaml  
- Priorities: 100 down to 60
- Default seeds: 0, 1, 2, 3, 4

### SLURM Integration

#### Most Reliable Method: Embedded Parameters

Use the embedded parameters script for maximum reliability:

```bash
# Submit workers to SLURM using embedded method
./scripts/submission/submit_slurm_embedded.sh \
    /path/to/experiment \
    experiment_name \
    workers_per_gpu \
    num_gpus

# Example: 3 workers per GPU, 8 GPUs total
./scripts/submission/submit_slurm_embedded.sh \
    /scratch/ddr8143/repos/myproject \
    my_experiment \
    3 \
    8
```

This method generates a temporary SLURM script with all parameters hardcoded, avoiding environment variable propagation issues.

#### Alternative Method: Explicit Export

```bash
# Using explicit export wrapper (also reliable)
./scripts/submission/submit_slurm_job.sh \
    /path/to/experiment \
    experiment_name \
    workers_per_gpu \
    num_gpus
```

## Monitoring Workflows

### Real-time Monitoring

```bash
# Check experiment status
dr_exp --experiment my_experiment status

# List all jobs by status
dr_exp --experiment my_experiment list --status all
dr_exp --experiment my_experiment list --status failed
dr_exp --experiment my_experiment list --status running

# Monitor in real-time
watch -n 30 'dr_exp --experiment my_experiment status'
```

### Custom Monitoring Scripts

The `scripts/` directory contains several monitoring utilities:

```bash
# Monitor GPU sharing
./scripts/monitor_gpu_sharing.sh

# Monitor launcher health
./scripts/monitor_launcher.sh

# Monitor specific experiment
./scripts/monitor_high_reg_experiment.sh
```

## Common Workflows

### 1. Standard Experiment Workflow

```bash
# 1. Submit experiment jobs
cd /path/to/project
./scripts/submission/submit_jobs.py --experiment-type chrono --dry-run  # Preview
./scripts/submission/submit_jobs.py --experiment-type chrono            # Submit

# 2. Launch workers via SLURM
./scripts/submission/submit_slurm_embedded.sh \
    /path/to/project \
    my_experiment \
    3 \
    8

# 3. Monitor progress
watch -n 30 'dr_exp --experiment my_experiment status'

# 4. Handle failures if needed
dr_exp --experiment my_experiment list --status failed
./scripts/submission/submit_jobs.py --retry-failed
```

### 2. Incremental Testing Workflow

```bash
# Test with one job first
./scripts/submission/submit_jobs.py --configs step00_baseline --seeds 0

# Monitor until completion
dr_exp --experiment test list --status all

# If successful, submit remaining
./scripts/submission/submit_jobs.py --experiment-type chrono
```

### 3. Recovery Workflow

```bash
# Check what failed
dr_exp --experiment my_experiment list --status failed

# Review submission logs
cat submission_logs/submission_*.json

# Retry with fixes
./scripts/submission/submit_jobs.py --retry-failed

# Or resubmit specific configs
./scripts/submission/submit_jobs.py --configs step00_baseline step01_sgd --force
```

## Project Structure Requirements

The submission scripts expect this project structure:

```
project_root/
├── configs/                    # Hydra configuration files
│   ├── model/                 # Model configurations
│   ├── optim/                 # Optimizer configurations
│   └── ...                    # Other config groups
├── scripts/                   # dr_exp utility scripts
│   └── submission/            # Submission utilities
├── experiment_name/           # Experiment data (created by dr_exp)
│   ├── jobs/                  # Job queue files
│   ├── storage/               # Job outputs
│   └── logs/                  # Worker logs
└── submission_logs/           # Submission transaction logs
```

## Error Handling and Troubleshooting

### Common Issues

**"Config files are missing"**
- Verify you're in the correct project directory
- Check that `configs/` directory exists with expected structure
- Ensure config file names match script expectations

**"Submission seems slow"**
- Scripts include small delays (0.1s) between submissions to prevent system overload
- Total time for 54 jobs: ~5 seconds

**"Jobs not starting"**
- Check SLURM queue: `squeue -u $USER`
- Verify workers are running: `ps aux | grep dr_exp`
- Check for resource constraints

**"Some jobs failed to submit"**
- Check submission logs in `submission_logs/`
- Use `--retry-failed` to resubmit failed jobs
- Review error messages for specific issues

### Debugging Commands

```bash
# Check job database status
dr_exp --experiment my_experiment status

# List recent submissions
ls -la submission_logs/

# Check SLURM job status
squeue -u $USER

# Monitor worker processes
ps aux | grep dr_exp

# Check system resources
nvidia-smi
df -h
```

## Best Practices

### Before Submitting
1. **Always use `--dry-run` first** to preview submissions
2. **Check existing jobs** with `dr_exp list` to avoid duplicates  
3. **Test with single job** before bulk submissions
4. **Verify configs exist** and are properly structured

### During Experiments
1. **Monitor early** to catch issues quickly
2. **Keep submission logs** for recovery purposes
3. **Check resource usage** (GPU, memory, disk)
4. **Review failed jobs promptly**

### After Completion
1. **Collect results** systematically
2. **Archive large outputs** to save space
3. **Clean up temporary files**
4. **Document lessons learned**

## Integration with Cluster Reference

This document focuses on project-specific workflows. For cluster infrastructure knowledge (hardware specs, SLURM configuration, troubleshooting), see the cluster reference documentation in `/Users/daniellerothermel/drotherm/repos/dr_ref/cluster/`.

**Complementary Documentation:**
- Cluster reference: General infrastructure and best practices
- This document: Project-specific submission and monitoring workflows
- API reference (`docs/api_reference.md`): Programmatic interfaces
- Quick start (`docs/quick_start_guide.md`): Getting started guide