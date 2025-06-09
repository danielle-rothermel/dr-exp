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

## 🔧 CONFIGURATION

### CLI-Based Configuration
All commands now require explicit configuration via CLI arguments. No environment variables needed for paths and modes.

### Required Arguments (All Commands)
- `--base-path /path/to/data` - Base directory for experiment data (jobs stored in `{base-path}/job_data/`)
- `--mode files_local|supabase_local|supabase_remote` - Database mode

### Optional Arguments
- `--storage-path /path/to/storage` - Storage directory for artifacts (defaults to `{base-path}/storage/`)

### Supabase Credentials (Environment Variables)
For security, Supabase credentials remain in environment variables:
- `SUPABASE_URL` - Supabase project URL (required for supabase modes)
- `SUPABASE_KEY` - Supabase service role key (required for supabase modes)

### Database Modes

#### Simple Testing (Files Local)
```bash
# No environment setup needed - all via CLI
# Commands use: --base-path ./logs --mode files_local
```
- Stores job data in JSON files at `./logs/job_data/`
- No database services required
- Good for isolated testing

#### Development (Supabase Local) 
```bash
# Start local Supabase
supabase start

# Commands use: --base-path ./logs --mode supabase_local
# Credentials automatically use local defaults
```
- Local PostgreSQL with web UI at `http://127.0.0.1:54323`
- Real-time features and API
- No credential setup needed for local mode

#### Production (Supabase Remote)
```bash
# Set credentials in environment
export SUPABASE_URL="your-project-url"
export SUPABASE_KEY="your-service-role-key"

# Commands use: --base-path ./logs --mode supabase_remote
```
- Cloud Supabase deployment
- Requires valid Supabase credentials in environment

**⚠️ Important:** Always use consistent `--base-path` and `--mode` across all commands in a workflow.

## 📋 COMMON WORKFLOWS

### Quick Dev Cycle (Supabase Local)
```bash
# 1. Start local Supabase (run once per session)
supabase start

# 2. Upload test jobs
uvrp scripts/upload_configs.py \
  --base-path ./logs \
  --mode supabase_local \
  --base-config-path configs \
  --config-name decon_config \
  --sweep "limit_train_batches=10 model=alexnet_cifar epochs=5" \
  --priority 150

# 3. Run worker
uv run python scripts/manager_cli.py \
  --base-path ./logs \
  --mode supabase_local \
  system run_worker dev_worker ./work
```

### Simple Testing Cycle (Files Local)
```bash
# 1. Upload test jobs (no setup needed)
uvrp scripts/upload_configs.py \
  --base-path ./logs \
  --mode files_local \
  --base-config-path configs \
  --config-name decon_config \
  --sweep "limit_train_batches=10 epochs=2" \
  --priority 150

# 2. Run worker
uv run python scripts/manager_cli.py \
  --base-path ./logs \
  --mode files_local \
  system run_worker dev_worker ./work
```

### Priority Management
```bash
# Upload urgent job
uvrp scripts/manager_cli.py \
  --base-path ./logs \
  --mode files_local \
  job upload_configs \
  --priority 800 \
  --sweep "..."

# Boost existing job
uvrp scripts/manager_cli.py \
  --base-path ./logs \
  --mode files_local \
  job boost_priority <job_id> \
  --amount 200

# Run single job immediately (bypasses queue)
uvrp scripts/manager_cli.py \
  --base-path ./logs \
  --mode files_local \
  job run_one \
  --overrides "model=resnet,lr=0.001"
```

### Debug and Diagnostics
```bash
# Show detailed system configuration
uv run python scripts/manager_cli.py \
  --base-path ./logs \
  --mode files_local \
  debug debug_config

# Perform comprehensive health check
uv run python scripts/manager_cli.py \
  --base-path ./logs \
  --mode files_local \
  debug debug_health_check

# Health check with verbose details
uv run python scripts/manager_cli.py \
  --base-path ./logs \
  --mode files_local \
  debug debug_health_check --verbose
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
**Symptoms:** `uv run python scripts/manager_cli.py --base-path ./logs --mode files_local job list_jobs` shows queued jobs, but worker completes with "no_job" status.

**Cause:** Configuration mismatch between job upload and worker execution.

**Debug Steps:**
1. **Run system health check** (recommended first step):
   ```bash
   uv run python scripts/manager_cli.py \
     --base-path ./logs \
     --mode files_local \
     debug debug_health_check --verbose
   ```

2. **Check configuration details**:
   ```bash
   uv run python scripts/manager_cli.py \
     --base-path ./logs \
     --mode files_local \
     debug debug_config
   ```

3. **Manual verification** (if needed):
   ```bash
   # For files_local mode, check if jobs exist in expected location
   ls -la ./logs/job_data/
   ```

4. **Fix:** Use consistent CLI arguments:
   ```bash
   # Ensure same --base-path and --mode for all commands
   uvrp scripts/upload_configs.py --base-path ./logs --mode files_local ...
   uv run python scripts/manager_cli.py --base-path ./logs --mode files_local system run_worker ...
   ```

#### Jobs Not Being Uploaded
**Symptoms:** Upload command succeeds but `job list_jobs` shows no jobs.

**Cause:** Different `--base-path` or `--mode` between upload and list commands.

**Fix:** Ensure same CLI arguments for all commands in workflow.

### Database Issues
- **"No such table"**: Run `supabase db reset` to apply migrations
- **Connection failures**: Check `--mode` argument matches database state (files_local vs supabase_local)
- **Stale data**: Use `scripts/reset_local_jobdb.py --base-path ./logs --mode files_local` for files_local mode

### Job Execution
- **Jobs stuck in queue**: Check priorities with `--base-path ./logs --mode files_local job list_jobs --status queued`
- **Worker not claiming**: Verify consistent `--base-path` and `--mode` between upload and worker commands
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
- Use `--mode files_local` for fast test cycles (no environment variables needed)
- Test complete workflows: upload → claim → execute → complete
- Verify priority ordering in job queues
- All tests use explicit `JobDBConfig(base_path=..., mode=...)` construction

### Development Debugging
- **API logs**: `uvicorn dr_exp.api.main:app --reload --log-level debug`
- **WebSocket**: Browser dev tools Network tab to see live updates
- **Database state**: Use Supabase Studio at `http://127.0.0.1:54323`
