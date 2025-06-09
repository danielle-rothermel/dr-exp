# dr_exp - Deep Learning Experiment Manager

## 🏗️ ARCHITECTURE OVERVIEW

### What This System Does
- Manages large-scale ML experiments on SLURM GPU clusters
- Priority-based job queue (0-1000) with smart scheduling
- Centralized data storage (Supabase) + real-time web monitoring
- Hydra-based config management with hyperparameter sweeps

### Core Components
```
src/dr_exp/
├── job_db/          # Database abstraction (BaseJobDB → LocalJobDB/SupabaseJobDB)
├── manage/          # Manager/Worker system + ProcessManager
├── api/             # FastAPI backend + WebSocket
├── logging/         # StructuredLogger for metrics/artifacts
├── cli/             # CLI Utility for using manage functionality
├── training/        # Training functions used by workers
└── utils/           # Factory, priority system helpers
```

### Key Design Patterns
- **Abstract Interface First**: All DB operations use `BaseJobDB` interface
- **Factory Pattern**: `Factory` creates integrated components with shared config
- **Priority-Based Scheduling**: Jobs have priorities 0-1000, highest runs first
- **Worker-Manager Model**: Manager coordinates, Workers execute training

## 🔧 ENVIRONMENT SETUP

### Required Environment Variables
- `EXPMGR_MODE`: Controls which database stores job data
- `DR_EXP_BASE_PATH`: Controls where job data and logs are stored

### Environment Modes

#### Simple Testing (Files Local)
Use for quick testing without database setup:
```bash
export EXPMGR_MODE=files_local
export DR_EXP_BASE_PATH="./logs"
```
- Stores job data in JSON files at `./logs/job_data/`
- No database services required
- Good for isolated testing

#### Development (Supabase Local) 
Use for full-featured local development:
```bash
export EXPMGR_MODE=supabase_local
export DR_EXP_BASE_PATH="./logs"
supabase start  # Local PostgreSQL with full features
```
- Local PostgreSQL with web UI
- Real-time features and API
- Visit: `http://127.0.0.1:54323` for database UI

#### Production (Supabase Remote)
```bash
export EXPMGR_MODE=supabase_remote
export DR_EXP_BASE_PATH="./logs"
export SUPABASE_URL="your-project-url"
export SUPABASE_KEY="your-service-role-key"
```
- Cloud Supabase deployment
- Requires valid Supabase credentials

**⚠️ Important:** Always use consistent environment variables across all commands in a workflow.

## 📋 COMMON WORKFLOWS

### Quick Dev Cycle (Supabase Local)
```bash
# 1. Set up environment (run once per session)
export EXPMGR_MODE=supabase_local
export DR_EXP_BASE_PATH="./logs"
supabase start

# 2. Upload test jobs
uvrp scripts/upload_configs.py \
  --base-config-path configs \
  --config-name decon_config \
  --sweep "limit_train_batches=10 model=alexnet_cifar epochs=5" \
  --priority 150

# 3. Run worker
uv run python scripts/manager_cli.py system run_worker dev_worker ./work
```

### Simple Testing Cycle (Files Local)
```bash
# 1. Set up environment (run once per session)
export EXPMGR_MODE=files_local
export DR_EXP_BASE_PATH="./logs"

# 2. Upload test jobs
uvrp scripts/upload_configs.py \
  --base-config-path configs \
  --config-name decon_config \
  --sweep "limit_train_batches=10 epochs=2" \
  --priority 150

# 3. Run worker
uv run python scripts/manager_cli.py system run_worker dev_worker ./work
```

### Priority Management
```bash
# Upload urgent job
uvrp scripts/manager_cli.py job upload_configs --priority 800 --sweep "..."

# Boost existing job
uvrp scripts/manager_cli.py job boost_priority <job_id> --amount 200

# Run single job immediately (bypasses queue)
uvrp scripts/manager_cli.py job run_one --overrides "model=resnet,lr=0.001"
```

## 🔍 KEY FILES & THEIR ROLES

### Database Layer (`src/dr_exp/job_db/`)
- `base_job_db.py` - **NEVER MODIFY**: Abstract interface contract
- `local_job_db.py` - JSON file implementation for testing
- `supabase_job_db.py` - PostgreSQL implementation for production

### Manager System (`src/dr_exp/manage/`)
- `manager.py` - Coordinates workers, claims jobs by priority
- `worker.py` - Executes training, logs metrics, handles errors
- `factory.py` - **START HERE**: Creates properly configured systems

### API & Frontend
- `src/dr_exp/api/main.py` - FastAPI app with WebSocket
- `react-babysitter-ui/` - Real-time monitoring interface
- Visit: `http://localhost:8000/docs` (API), `http://localhost:5173` (UI)

## ⚠️ CRITICAL CONSTRAINTS

### Database Abstraction Rules
- **Manager ONLY uses BaseJobDB methods** - no database-specific code
- **Never bypass the interface** - all DB access through job_db layer
- **Factory creates integrated components** - don't instantiate directly

### Priority System Rules
- **0-1000 range**: 0=lowest, 1000=highest
- **System jobs (900-1000)**: Critical maintenance only
- **Urgent jobs (700-899)**: Deadlines, "run one" functionality
- **Normal jobs (100-399)**: Default range

### SLURM Integration
- Workers designed for multi-GPU SLURM environments
- Use `scripts/slurm_job.sbatch` for cluster submission
- Manager handles `--gpus-per-node` and `--workers-per-gpu` scaling

## 🚨 TROUBLESHOOTING

### Configuration Issues

#### Worker Reports "no_job" But Jobs Exist
**Symptoms:** `uv run python scripts/manager_cli.py job list_jobs` shows queued jobs, but worker completes with "no_job" status.

**Cause:** Configuration mismatch between job upload and worker execution.

**Debug Steps:**
1. Check environment variables are consistent:
   ```bash
   echo "EXPMGR_MODE: $EXPMGR_MODE"
   echo "DR_EXP_BASE_PATH: $DR_EXP_BASE_PATH"
   ```

2. Verify job storage location:
   ```bash
   # For files_local mode, check if jobs exist in expected location
   ls -la ./logs/job_data/
   
   # If jobs are elsewhere, find them:
   find . -name "*.json" -path "*/job_data/*" 2>/dev/null
   ```

3. **Fix:** Use consistent environment variables:
   ```bash
   export EXPMGR_MODE=files_local
   export DR_EXP_BASE_PATH="./logs"
   # Run both upload and worker commands with same environment
   ```

#### Jobs Not Being Uploaded
**Symptoms:** Upload command succeeds but `job list_jobs` shows no jobs.

**Cause:** Different `DR_EXP_BASE_PATH` between upload and list commands.

**Fix:** Ensure same environment for all commands in workflow.

### Database Issues
- **"No such table"**: Run `supabase db reset` to apply migrations
- **Connection failures**: Check `EXPMGR_MODE` environment variable matches database state
- **Stale data**: Use `scripts/reset_local_jobdb.py` for files_local mode

### Job Execution
- **Jobs stuck in queue**: Check priorities with `job list_jobs --status queued`
- **Worker not claiming**: Verify consistent `DR_EXP_BASE_PATH` between upload and worker
- **Training failures**: Check `StructuredLogger` setup in worker code

### Configuration
- **Hydra configs live in**: `configs/`
- **Override syntax**: `model=resnet,vit lr=0.01,0.001` (comma-separated values)
- **Custom configs**: Place in configs/ directory, reference by name

## 🧪 TESTING PATTERNS

### Unit Tests
- Database layer: Test against both LocalJobDB and SupabaseJobDB
- Manager: Mock BaseJobDB interface, test job claiming logic
- API: Use FastAPI test client with auth tokens

### Integration Tests
- Use `EXPMGR_MODE=files_local` for fast test cycles
- Test complete workflows: upload → claim → execute → complete
- Verify priority ordering in job queues

### Development Debugging
- **API logs**: `uvicorn dr_exp.api.main:app --reload --log-level debug`
- **WebSocket**: Browser dev tools Network tab to see live updates
- **Database state**: Use Supabase Studio at `http://127.0.0.1:54323`
