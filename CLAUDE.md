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

## 🔧 ENVIRONMENT MODES

- `EXPMGR_MODE`: Controls which database stores job data
- `DR_EXP_BASE_PATH`: Controls where logs are written (always use a path prefixed by  `./logs/`)

### Simple Testing
```bash
export EXPMGR_MODE=files_local  # JSON files in job_data/
```

### Development (Always Use)
```bash
export EXPMGR_MODE=supabase_local
supabase start  # Local PostgreSQL with full features
```

### Production
```bash
export EXPMGR_MODE=supabase_remote  # Cloud Supabase
```

## 📋 COMMON WORKFLOWS

### Quick Dev Cycle
```bash
# 1. Start services
supabase start
export EXPMGR_MODE=supabase_local

# 2. Upload test jobs
uvrp scripts/upload_configs.py \
  --base-config-path configs \
  --config-name decon_config \
  --sweep "limit_train_batches=10 model=alexnet_cifar epochs=5" \
  --priority 150

# 3. Run worker
DR_EXP_BASE_PATH="./logs/test0" uv run python scripts/manager_cli.py system run-worker dev_worker ./work
```

### Priority Management
```bash
# Upload urgent job
uvrp scripts/manager_cli.py job upload-configs --priority 800 --sweep "..."

# Boost existing job
uvrp scripts/manager_cli.py job boost-priority <job_id> --amount 200

# Run single job immediately (bypasses queue)
uvrp scripts/manager_cli.py job run-one --overrides "model=resnet,lr=0.001"
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

## 🚨 COMMON GOTCHAS

### Database Issues
- **"No such table"**: Run `supabase db reset` to apply migrations
- **Connection failures**: Check `EXPMGR_MODE` environment variable
- **Stale data**: Use `scripts/reset_local_jobdb.py` for files_local mode

### Job Execution
- **Jobs stuck in queue**: Check priorities with `job list-jobs --status queued`
- **Worker not claiming**: Ensure `job_id` reserved correctly in database
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
