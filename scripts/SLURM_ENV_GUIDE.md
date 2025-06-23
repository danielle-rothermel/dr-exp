# SLURM Environment Variable Guide

## The Problem

SLURM's `--export=ALL` doesn't always work as expected due to:
- Cluster-specific CLI filters that override defaults
- Known bugs with srun propagation
- Multi-node job complications
- Job submission portal limitations

## Solutions (Most to Least Reliable)

### 1. **Embedded Parameters** (100% Reliable) ✅
Generate a temporary sbatch script with all values hardcoded:
```bash
./scripts/submit_slurm_embedded.sh /path/to/exp experiment_name workers_per_gpu num_gpus
```
This method embeds all parameters directly in the script - no environment variables needed.

### 2. **Explicit Export** (Very Reliable) ✅
Export variables AND pass them explicitly:
```bash
./scripts/submit_slurm_job.sh /path/to/exp experiment_name workers_per_gpu num_gpus
```
This uses both `export` before sbatch and `--export=ALL,VAR=value` syntax.

### 3. **Direct sbatch with --export** (Usually Works)
```bash
sbatch --export=ALL,BASE_PATH=/path,EXPERIMENT=name,WORKERS_PER_GPU=4 scripts/slurm_job_safe.sbatch
```

### 4. **Environment Export** (May Not Work)
```bash
export BASE_PATH=/path
export EXPERIMENT=name
sbatch scripts/slurm_job.sbatch  # Relies on --export=ALL
```

## Testing Your Cluster

Test if `--export=ALL` works on your cluster:
```bash
# Test script
export TEST_VAR="hello_world"
sbatch --wrap='echo "TEST_VAR=$TEST_VAR"' --export=ALL
```

If it prints "TEST_VAR=hello_world", then --export=ALL works.
If it prints "TEST_VAR=", then use methods 1 or 2 above.

## For dr_exp Experiments

### Quick Start (Most Reliable)
```bash
# 1. Submit your experiment jobs
python scripts/submit_experiments.sh

# 2. Launch workers using embedded script
./scripts/submit_slurm_embedded.sh \
    /scratch/ddr8143/repos/dr_exp/chronological_ablation \
    main \
    3 \
    2  # 3 workers/GPU, 2 GPUs = 6 total workers
```

### Alternative (Also Reliable)
```bash
# Using explicit export wrapper
./scripts/submit_slurm_job.sh \
    /scratch/ddr8143/repos/dr_exp/chronological_ablation \
    main \
    3 \
    2
```

## Debugging

If variables aren't passing through:
1. Check the SLURM output logs for the "Environment check" section
2. Look for the parameter values being printed
3. If they show defaults instead of your values, switch to method 1 or 2

## Files Reference

- `slurm_job.sbatch` - Original script (requires env vars)
- `slurm_job_safe.sbatch` - Improved with better logging
- `submit_slurm_job.sh` - Wrapper using explicit export
- `submit_slurm_embedded.sh` - Generates script with embedded values
- `dr_exp_cluster.sbatch` - Production-ready alternative