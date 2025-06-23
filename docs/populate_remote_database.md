# How to Populate the Remote Supabase Database

This guide shows how to use the dr_exp CLI to create data in all three remote database tables: `experiments`, `jobs`, and `sync_status`.

## Prerequisites

1. Ensure your `.env` file contains:
   ```bash
   SUPABASE_URL=https://yfawygsfsuwrqvohsayp.supabase.co
   SUPABASE_KEY=<your-service-role-key>
   ```

2. Verify connection:
   ```bash
   uvrp scripts/test_remote_supabase.py
   ```

## Data Flow Overview

The dr_exp system populates the remote database through these paths:

1. **experiments table**: Created automatically when a worker with sync enabled starts
2. **jobs table**: Synced when workers process jobs with sync enabled
3. **sync_status table**: Created when workers upload files (metrics, models, logs)

## Step-by-Step Operations

### 1. Initialize a Local Experiment

First, create a local experiment directory:

```bash
uv run dr_exp --base-path ./test_experiments --experiment remote_test init
```

### 2. Create a Test Configuration

Create a config file at `configs/test_remote.yaml`:

```yaml
_target_: dr_exp.trainers.test_trainer.train

# Test parameters
epochs: 2
batch_size: 32
simulate_metrics: true
save_outputs: true

# Model config
model:
  name: test_model
  hidden_size: 128

# Training config  
optimizer:
  lr: 0.001
```

### 3. Submit Jobs to the Local Queue

Submit a few test jobs with different priorities:

```bash
# High priority job
uv run dr_exp --base-path ./test_experiments --experiment remote_test job submit \
  --config-name test_remote --priority 900

# Normal priority job
uv run dr_exp --base-path ./test_experiments --experiment remote_test job submit \
  --config-name test_remote --priority 100 \
  --overrides "epochs=5,model.hidden_size=256"

# Low priority job
uv run dr_exp --base-path ./test_experiments --experiment remote_test job submit \
  --config-name test_remote --priority 10 \
  --overrides "optimizer.lr=0.01"
```

### 4. Check Local Job Queue

Verify jobs were created locally:

```bash
uv run dr_exp --base-path ./test_experiments --experiment remote_test job list
```

### 5. Run a Worker with Sync Enabled

This is where the remote database gets populated:

```bash
# Run worker with sync enabled (uses SUPABASE_URL/KEY from environment)
uv run dr_exp --base-path ./test_experiments --experiment remote_test worker \
  --worker-id worker_01 \
  --working-dir ./work/worker_01
```

## What Happens During Worker Execution

1. **On Worker Start**:
   - Worker initializes `SyncHandler`
   - `SyncHandler` calls `get_or_create_experiment()` → **Creates entry in `experiments` table**

2. **When Processing Each Job**:
   - Worker claims a job from local queue
   - Worker executes the job (runs the trainer)
   - If job produces outputs (metrics, models, logs):
     - Files are added to the sync queue
     - Background sync thread uploads files to storage
     - **Creates entries in `sync_status` table** for each file
   - On job completion:
     - Worker calls `sync_job()` → **Creates/updates entry in `jobs` table**

3. **Background Sync Process**:
   - Continuously processes the sync queue
   - Updates `sync_status` entries as files upload
   - Handles retries for failed uploads

## Verifying Remote Data

After running the worker, check the remote database:

```bash
# Run the verification script
uvrp scripts/check_remote_db.py
```

Or check manually via the Supabase dashboard:
- https://supabase.com/dashboard/project/yfawygsfsuwrqvohsayp/editor

You should see:
- 1 row in `experiments` table
- 3 rows in `jobs` table (one for each submitted job)
- Multiple rows in `sync_status` table (one for each output file)

## Advanced: Multi-Worker Setup

To see more interesting data patterns, run multiple workers:

```bash
# Terminal 1
uv run dr_exp --base-path ./test_experiments --experiment remote_test worker \
  --worker-id worker_01 --working-dir ./work/worker_01

# Terminal 2  
uv run dr_exp --base-path ./test_experiments --experiment remote_test worker \
  --worker-id worker_02 --working-dir ./work/worker_02

# Terminal 3 - Submit more jobs while workers are running
uv run dr_exp --base-path ./test_experiments --experiment remote_test job submit \
  --config-name test_remote --priority 500
```

## Using the SLURM Launcher

For automatic multi-worker deployment with GPU discovery:

```bash
# This creates multiple workers based on available GPUs
uv run dr_exp --base-path ./test_experiments --experiment remote_test system launcher \
  --workers-per-gpu 2
```

## Remote-Only Operations (Read)

To list experiments from remote:

```python
# Currently requires custom script - not in CLI yet
from dr_exp.sync.supabase_client import SupabaseClient

client = SupabaseClient()
experiments = client.client.table("experiments").select("*").execute()
for exp in experiments.data:
    print(f"Experiment: {exp['experiment_name']} (ID: {exp['id']})")
```

## Summary

The key to populating the remote database is running workers with sync enabled. The data flow is:

1. **Local Operations**: `uv run dr_exp job submit` → Creates jobs locally only
2. **Sync Operations**: `uv run dr_exp worker` (with sync) → Syncs to remote database
3. **Remote Population**:
   - `experiments` table: One row per unique experiment
   - `jobs` table: One row per job processed by workers
   - `sync_status` table: One row per file uploaded to storage

This design allows the system to work offline (local-only) and sync to the cloud when connectivity is available.