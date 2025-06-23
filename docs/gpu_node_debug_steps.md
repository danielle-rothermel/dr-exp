# GPU Node Debug Steps for dr_exp

## Context
This debug sequence is designed to verify dr_exp functionality on a SLURM GPU node. The system has already been tested on the login node with basic job submission working correctly.

**Current State**:
- Repository location: `/scratch/ddr8143/repos/dr_exp`
- Test directory: `/scratch/ddr8143/repos/dr_exp/test_runs`
- Experiment name: `basic_test`
- 4 jobs already queued (submitted from login node)
- Running in Singularity container with GPU support

**Environment Setup**:
```bash
# You're in a Singularity container started with:
# singularity exec --nv --overlay /scratch/ddr8143/drexp.ext3:rw /scratch/work/public/singularity/cuda11.8.86-cudnn8.7-devel-ubuntu22.04.2.sif /bin/bash

# Set working directory and test path
cd /scratch/ddr8143/repos/dr_exp
export TEST_DIR=/scratch/ddr8143/repos/dr_exp/test_runs
```

## GPU Debug Steps

### Step 1: Verify GPU Environment
```bash
# Check GPU visibility
nvidia-smi
python -c "import torch; print(f'PyTorch CUDA available: {torch.cuda.is_available()}'); print(f'GPU count: {torch.cuda.device_count()}')"

# Check current job queue status
uv run dr_exp --base-path $TEST_DIR --experiment basic_test status
uv run dr_exp --base-path $TEST_DIR --experiment basic_test list --status queued
```
**Expected**: Should see GPU(s) available and 4 queued jobs

### Step 2: Single Worker GPU Execution
```bash
# Run one worker to process a single job
uv run dr_exp --base-path $TEST_DIR --experiment basic_test worker \
  --worker-id gpu_test_worker \
  --max-jobs 1 \
  --working-dir $TEST_DIR/work
```
**Expected**: 
- Worker claims highest priority job (priority 500)
- Executes DeconCNN training on GPU
- Shows training progress
- Completes successfully
- Creates output in `storage/run_<job_id>/`

### Step 3: Verify Results
```bash
# Check job completed
uv run dr_exp --base-path $TEST_DIR --experiment basic_test list --status completed

# Find the completed job's storage
COMPLETED_JOB=$(uv run dr_exp --base-path $TEST_DIR --experiment basic_test list --status completed | grep -o '[a-f0-9-]\{36\}' | head -1)
echo "Completed job ID: $COMPLETED_JOB"

# Check outputs
ls -la $TEST_DIR/basic_test/storage/run_${COMPLETED_JOB}/
cat $TEST_DIR/basic_test/storage/run_${COMPLETED_JOB}/final_metrics.json

# Check if logs were created
ls -la $TEST_DIR/basic_test/logs/
```
**Expected**: Job output directory contains model checkpoints, metrics, and logs

### Step 4: GPU Discovery Test
```bash
# Test GPU discovery for launcher
uv run python -c "
from pathlib import Path
from dr_exp.worker.launcher import WorkerLauncher
from dr_exp.core.job_db import JobDB

# Create minimal launcher to test GPU discovery
job_db = JobDB('$TEST_DIR', 'basic_test')
launcher = WorkerLauncher(job_db, 'basic_test', Path('$TEST_DIR/logs'), 1)
gpus = launcher.discover_gpus()
print(f'GPUs discovered: {gpus}')
print(f'Number of GPUs: {len(gpus)}')
"
```
**Expected**: Should list GPU indices available to the container

### Step 5: Concurrent Worker Test
```bash
# Submit a few more jobs for concurrent testing
for i in {1..3}; do
  uv run dr_exp --base-path $TEST_DIR --experiment basic_test job submit \
    --config-path configs --config-name decon_config --priority $((600 + i*10))
done

# Run 2 workers concurrently on the same GPU
for i in {1..2}; do
  uv run dr_exp --base-path $TEST_DIR --experiment basic_test worker \
    --worker-id gpu_worker_$i \
    --max-jobs 2 \
    --working-dir $TEST_DIR/work_$i &
done

# Wait for completion
wait

# Check results
uv run dr_exp --base-path $TEST_DIR --experiment basic_test status
```
**Expected**: 
- Both workers process jobs without conflicts
- No double-claiming of jobs
- Jobs processed in priority order

### Step 6: Brief Launcher Test (Optional)
```bash
# Test launcher for 30 seconds
timeout 30 uv run dr_exp --base-path $TEST_DIR --experiment basic_test launcher \
  --workers-per-gpu 2 \
  --max-hours 0.001 2>&1 | tee $TEST_DIR/launcher_test.log

# Check launcher created workers
grep "Spawning worker" $TEST_DIR/launcher_test.log
```
**Expected**: Launcher spawns workers-per-gpu × number of GPUs

## Troubleshooting Guide

### If GPU not visible:
```bash
# Check CUDA environment
echo $CUDA_VISIBLE_DEVICES
env | grep CUDA

# Test with explicit GPU setting
CUDA_VISIBLE_DEVICES=0 python -c "import torch; print(torch.cuda.is_available())"
```

### If worker fails to start:
```bash
# Check for import errors
uv run python -c "from dr_exp.trainers.decon_trainer import train_decon; print('Import successful')"

# Try with verbose output
uv run dr_exp --base-path $TEST_DIR --experiment basic_test worker \
  --worker-id debug_verbose \
  --max-jobs 1 \
  --working-dir $TEST_DIR/work_debug 2>&1 | tee worker_debug.log
```

### If file locking errors:
```bash
# Check filesystem type
df -T $TEST_DIR

# Test basic file locking
uv run python -c "
import fcntl
with open('$TEST_DIR/lock_test', 'w') as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    print('Lock acquired successfully')
"
```

### If training fails:
```bash
# Check error output
FAILED_JOB=$(uv run dr_exp --base-path $TEST_DIR --experiment basic_test list --status failed | grep -o '[a-f0-9-]\{36\}' | head -1)
cat $TEST_DIR/basic_test/storage/run_${FAILED_JOB}/error.txt
```

## Success Criteria

The system is ready for SLURM batch jobs if:
1. ✅ Worker successfully processes job on GPU
2. ✅ Training outputs saved to correct location  
3. ✅ Concurrent workers don't conflict
4. ✅ GPU discovery works correctly
5. ✅ File locking works on cluster filesystem

## Next Steps After Success

Once these tests pass, you can:
1. Submit SLURM batch jobs using `sbatch dr_exp_slurm.sbatch`
2. Use the launcher for multi-GPU job processing
3. Submit parameter sweeps for large experiments
4. Monitor progress using `dr_exp slurm status`

## Quick Reference

**Common Commands**:
```bash
# Check status
uv run dr_exp --base-path $TEST_DIR --experiment basic_test status

# List jobs by status
uv run dr_exp --base-path $TEST_DIR --experiment basic_test list --status queued
uv run dr_exp --base-path $TEST_DIR --experiment basic_test list --status running
uv run dr_exp --base-path $TEST_DIR --experiment basic_test list --status completed

# Submit more test jobs
uv run dr_exp --base-path $TEST_DIR --experiment basic_test job submit \
  --config-path configs --config-name decon_config --priority 999

# Check sync queue
uv run dr_exp --base-path $TEST_DIR --experiment basic_test sync-status
```

**File Locations**:
- Jobs: `$TEST_DIR/basic_test/jobs/*.json`
- Storage: `$TEST_DIR/basic_test/storage/run_*/`
- Logs: `$TEST_DIR/basic_test/logs/`
- Control: `$TEST_DIR/basic_test/control/`