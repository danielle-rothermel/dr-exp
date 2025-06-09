# DR_EXP Implementation Summary & Quick Reference

## Overview

This document provides a quick reference for the complete DR_EXP redesign implementation. The new architecture eliminates complexity in favor of a simple, predictable system.

## Key Architecture Decisions

1. **Single JobDB Implementation**: No more LocalJobDB vs SupabaseJobDB complexity
2. **Base Path + Experiment Name**: Supports user directories in /scratch (e.g., `/scratch/users/jane/experiments/resnet_sweep`)
3. **Local First, Remote Second**: Always write to /scratch, sync to Supabase for remote access
4. **Embedded Sync**: Workers handle their own background sync, no separate services
5. **Start Local**: API testing locally before cloud deployment
6. **Built-in Concurrency**: File locking in JobDB eliminates need for distributed coordination
7. **Hydra-based Dispatch**: Jobs specify their trainer via `_target_`, no hardcoded dispatch logic
8. **Operational CLI**: Unified `dr_exp` command for all operations

## Implementation Phases

### Phase 1: Clean Slate (3-4 days)
**Goal**: Remove all legacy code and create simple JobDB

```bash
# Key files to create:
src/dr_exp/core/job_db.py  # Single JobDB class

# Test with:
python test_job_db.py
```

### Phase 2: Worker Integration (3-4 days)
**Goal**: Workers with embedded sync threads

```bash
# Key files to create:
src/dr_exp/sync/queue.py           # Sync queue management
src/dr_exp/worker/base.py          # Base worker with sync
src/dr_exp/worker/training_worker.py  # ML training worker

# Test with:
python test_worker.py
```

### Phase 3: Supabase Integration (3-4 days)
**Goal**: Real uploads to Supabase for remote access

```bash
# Key files to create:
src/dr_exp/sync/supabase_client.py  # Supabase operations

# Setup:
1. Create Supabase project
2. Run SQL schema
3. Create .env file
4. Test with:
python test_supabase_integration.py
```

### Phase 4: API Local Testing (2-3 days)
**Goal**: API working locally before deployment

```bash
# Key files to create:
src/dr_exp/api/simple_api.py  # FastAPI application

# Test with:
python test_api_local.py
# Then open test_frontend.html in browser
```

### Phase 5: Cloud Deployment (1-2 days) [Optional]
**Goal**: Deploy API to Vercel for true remote access

```bash
# Key files to create:
api/index.py      # Vercel entry point
vercel.json       # Vercel config
requirements.txt  # Dependencies

# Deploy:
vercel --prod
```

### Phase 6: Migration & Cleanup (2 days)
**Goal**: Storage management tools

```bash
# Key files to create:
src/dr_exp/tools/storage_scanner.py  # Scan storage usage
src/dr_exp/tools/cleanup.py          # Interactive cleanup
cleanup_experiments.py                # CLI entry point

# Use:
python cleanup_experiments.py /scratch/users/jane/experiments
```

## Quick Command Reference

### CLI Commands

```bash
# Submit jobs
dr_exp --base-path /scratch/exp --experiment my_exp submit config.yaml --priority 500

# List jobs
dr_exp --base-path /scratch/exp --experiment my_exp list --status queued

# Run worker
dr_exp --base-path /scratch/exp --experiment my_exp worker --worker-id gpu_1

# Kill a job
dr_exp --base-path /scratch/exp --experiment my_exp kill job_id

# Boost priority
dr_exp --base-path /scratch/exp --experiment my_exp boost job1 job2 --priority 900

# Recover stale jobs
dr_exp --base-path /scratch/exp --experiment my_exp recover

# Run single job (debugging)
dr_exp --base-path /scratch/exp --experiment my_exp run_one job_id --no-sync

# Start API locally
export DR_EXP_BASE_PATH=/scratch/users/jane/experiments
export DR_EXP_EXPERIMENT=test_exp
uvicorn dr_exp.api.simple_api:app --reload
```

### Operational Commands

```bash
# Scan storage usage
python cleanup_experiments.py /scratch/users/jane/experiments --scan-only

# Interactive cleanup
python cleanup_experiments.py /scratch/users/jane/experiments

# Dry run cleanup (see what would be deleted)
python cleanup_experiments.py /scratch/users/jane/experiments --dry-run
```

## Directory Structure

```
/scratch/users/jane/experiments/  # Base path
└── resnet_sweep/                 # Experiment name
    ├── jobs/                     # Job metadata (JSON files)
    │   ├── job_uuid1.json
    │   └── job_uuid2.json
    ├── storage/                  # All artifacts
    │   ├── run_job_uuid1/
    │   │   ├── metrics.jsonl
    │   │   ├── training.log
    │   │   └── model_final.pt
    │   └── run_job_uuid2/
    └── sync_queue/               # Pending uploads
        └── timestamp_file.json
```

## Config Structure

All job configs must include `_target_` field pointing to the training function:

```yaml
# Example: configs/experiments/decon/resnet18.yaml
_target_: dr_exp.trainers.decon_trainer.train_classification

# Training function parameters
model:
  architecture: resnet18
  num_classes: 10

optim:
  name: adamw
  lr: 0.001

epochs: 100
batch_size: 128
```

The worker will call `hydra.utils.call(config)` which instantiates and calls the target function.

## Environment Variables

### For Workers (on cluster)
```bash
# No environment variables needed - pass paths directly
```

### For API (local or cloud)
```bash
DR_EXP_BASE_PATH=/scratch/users/jane/experiments
DR_EXP_EXPERIMENT=resnet_sweep
SUPABASE_URL=https://xxx.supabase.co  # For remote features
SUPABASE_KEY=xxx                      # For remote features
```

## Common Operations

### Create and Run Experiment

```bash
# 1. Create config files
cat > configs/exp1.yaml << EOF
_target_: dr_exp.trainers.decon_trainer.train_classification
model:
  architecture: resnet18
optim:
  lr: 0.001
batch_size: 32
epochs: 100
EOF

# 2. Submit jobs
dr_exp --base-path /scratch/users/jane/experiments \
       --experiment hyperparameter_search_v1 \
       submit configs/exp1.yaml

# 3. Run workers (on compute nodes)
dr_exp --base-path /scratch/users/jane/experiments \
       --experiment hyperparameter_search_v1 \
       worker --worker-id node1_gpu0
```

### Handle Common Issues

```bash
# Job stuck/crashed
dr_exp --base-path /scratch/exp --experiment my_exp list --status running
dr_exp --base-path /scratch/exp --experiment my_exp kill stuck_job_id
dr_exp --base-path /scratch/exp --experiment my_exp recover

# Emergency priority boost
dr_exp --base-path /scratch/exp --experiment my_exp boost urgent_job --priority 950

# Debug failing job locally
dr_exp --base-path /scratch/exp --experiment my_exp run_one failing_job_id --no-sync
```

### Monitor Remotely (after Phase 4)
```bash
# On cluster: Start API
export DR_EXP_BASE_PATH=/scratch/users/jane/experiments
export DR_EXP_EXPERIMENT=hyperparameter_search_v1
uvicorn dr_exp.api.simple_api:app --host 0.0.0.0 --port 8000

# From laptop: SSH tunnel
ssh -L 8000:localhost:8000 cluster.example.com

# Open browser to http://localhost:8000
```

### Clean Up Old Experiments
```bash
# See what you have
python cleanup_experiments.py /scratch/users/jane/experiments --scan-only

# Clean experiments older than 30 days
python cleanup_experiments.py /scratch/users/jane/experiments
# Then select option 2 and enter 30
```

## Troubleshooting

### "No jobs available" but jobs exist
- Check base_path and experiment_name match between job creation and worker
- Verify jobs are in "queued" status
- Check file permissions in experiment directory

### Sync not working
- Verify .env file has correct Supabase credentials
- Check worker logs for sync errors
- Ensure Supabase bucket exists ("experiments")

### API can't find jobs
- Verify DR_EXP_BASE_PATH and DR_EXP_EXPERIMENT environment variables
- Check that JobDB was initialized with enable_remote_read=True
- Ensure jobs have been synced to Supabase (check sync_queue/)

## Design Principles to Maintain

1. **Fail Fast**: Use assertions, not exceptions
2. **No Hidden Behavior**: Everything is explicit
3. **Single Source of Truth**: /scratch is authoritative
4. **Simple Over Clever**: Direct, obvious code
5. **No Backwards Compatibility**: Clean breaks when improving

## What We Eliminated

- ❌ Complex factory patterns
- ❌ Abstract base classes for everything  
- ❌ Multiple storage modes
- ❌ Configuration files
- ❌ Hidden caching behavior
- ❌ Bidirectional sync
- ❌ Complex CLI framework

## What We Gained

- ✅ Predictable storage locations
- ✅ Simple, direct code
- ✅ Clear data flow (cluster → Supabase)
- ✅ Easy debugging
- ✅ Minimal dependencies
- ✅ Fast development
- ✅ Easy to understand and modify

The new system is intentionally simple. Resist the urge to add complexity!