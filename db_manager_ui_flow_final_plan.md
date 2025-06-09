# DR_EXP Architecture Redesign: Cloud-First Experiment Management

Executive Summary

This document outlines a complete architectural redesign of the DR_EXP experiment management system to support remote monitoring of
SLURM cluster experiments. The redesign prioritizes simplicity, reliability, and remote accessibility while respecting cluster IO
constraints.

## 1. Background and Constraints

1.1 Cluster Environment Constraints

- No persistent services: All jobs on login nodes are killed daily
- No cron jobs: Automated scheduling is prohibited
- IO throttling: Excessive external IO from cluster is discouraged
- Limited compute on login nodes: Heavy operations require SLURM job submission
- Shared storage: All nodes have access to /scratch filesystem

1.2 User Requirements

- Remote monitoring: View job status and metrics while traveling without SSH
- Real-time updates: See training progress as it happens
- Log access: Read worker logs without cluster connection
- Rich analytics: Query across experiments without cluster load
- Simple deployment: Minimal operational complexity

1.3 Current Architecture Problems

- Hidden storage behaviors: SupabaseJobDB creates unexpected local caches
- Inconsistent storage patterns: Different modes store data differently
- Complex hybrid approach: Mixing local and remote storage creates confusion
- No clear data flow: Unclear when data is local vs remote
- Difficult cleanup: Storage scattered across multiple locations

## 2. Design Decisions

### 2.1 Core Architecture: Supabase as Read Replica

Decision: Use /scratch as authoritative storage, Supabase as read-optimized replica

Justification:
- Workers always have fast local writes (no network failures during training)
- Cluster IO is minimized (controlled background sync)
- Remote access is optimized (queries hit Supabase, not cluster)
- Clear data flow (cluster → Supabase, never reverse)
- Simple failure recovery (re-sync from /scratch)

### 2.2 Storage Hierarchy

Decision: Single storage pattern across all modes

```
/scratch/experiments/{experiment_name}/
├── jobs/                 # Job metadata (JSON files)
├── storage/              # All artifacts
│   └── run_{job_id}/
│       ├── metrics.jsonl
│       ├── worker.log
│       ├── model_checkpoint.pt
│       └── .sync_status.json
└── sync_queue/           # Pending upload tracking
```

Justification:
- Predictable structure regardless of mode
- Easy to understand and debug
- Simple cleanup (delete one directory)
- Clear sync status tracking

### 2.3 Sync Strategy: Embedded Background Thread

Decision: Each worker runs its own sync thread with rate limiting

Justification:
- No separate sync service to manage
- Sync continues even if some workers fail
- Natural load distribution across workers
- Rate limiting prevents IO throttling
- Progressive upload enables real-time monitoring

### 2.4 API Deployment: Stateless Cloud Function

Decision: Deploy API as stateless function on Vercel/Railway

Justification:
- Zero maintenance (no servers to manage)
- Always available (survives cluster downtime)
- Scales automatically
- Simple deployment (git push)
- Free tier sufficient for personal use

### 2.5 Complete Rewrite Strategy

Decision: Remove all legacy code and backwards compatibility

Justification:
- Clean, intuitive codebase
- No hidden behaviors
- Easier to understand and maintain
- Faster development without legacy constraints
- Clear migration path (stop old system, start new)

## 3. End-to-End Architecture

### 3.1 Data Flow

```
┌─────────────────────────────── SLURM Cluster ───────────────────────────────┐
│                                                                             │
│  1. Worker Process                           2. Background Sync Thread      │
│     │                                           │                           │
│     ├─ Write metrics → /scratch/storage/        ├─ Read sync queue          │
│     ├─ Write logs → /scratch/storage/           ├─ Upload to Supabase       │
│     ├─ Write artifacts → /scratch/storage/      ├─ Update sync status       │
│     └─ Queue for sync → /scratch/sync_queue/    └─ Sleep 5 minutes          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓ HTTPS (Rate Limited)
                                    │
┌─────────────────────────────── Internet ────────────────────────────────────┐
│                                                                             │
│  3. Supabase Cloud                          4. API Layer (Vercel)           │
│     │                                           │                           │
│     ├─ PostgreSQL (job metadata)                ├─ Query Supabase DB        │
│     ├─ Storage Bucket (artifacts)               ├─ Serve metrics            │
│     └─ Realtime subscriptions                   └─ WebSocket updates        │
│                                                 │                           │
│                                                 ↓ HTTPS                     │
│                                                                             │
│  5. React Frontend                                                          │
│     ├─ Show job status                                                      │
│     ├─ Plot metrics                                                         │
│     └─ Display logs                                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Specifications

#### 3.2.1 Worker with Embedded Sync

```
class Worker:
  def __init__(self, job_id: str, config: dict):
      self.job_id = job_id
      self.storage_dir = f"/scratch/experiments/{config['experiment']}/storage/run_{job_id}"
      self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
      self.sync_thread.start()

  def train(self):
      for epoch in range(self.epochs):
          # Training logic
          metrics = {"epoch": epoch, "loss": loss, "accuracy": acc}

          # Write locally (immediate, reliable)
          self._write_metrics(metrics)

          # Queue for background sync
          self._queue_sync("metrics.jsonl")

  def _sync_loop(self):
      """Background thread that syncs to Supabase with rate limiting"""
      while self.active:
          pending = self._get_pending_syncs()

          for item in pending[:10]:  # Batch limit
              if self._upload_to_supabase(item):
                  self._mark_synced(item)

              time.sleep(1)  # Rate limit between files

          time.sleep(300)  # 5 minutes between sync cycles
```

#### 3.2.2 Simplified JobDB Implementation
```
class JobDB:
  """Single implementation - no more LocalJobDB vs SupabaseJobDB split"""

  def __init__(self, experiment_name: str, supabase_url: str = None):
      self.base_path = f"/scratch/experiments/{experiment_name}"
      self.jobs_dir = f"{self.base_path}/jobs"
      self.storage_dir = f"{self.base_path}/storage"

      # Supabase is optional (None for worker-only mode)
      if supabase_url:
          self.supabase = create_client(supabase_url, supabase_key)
      else:
          self.supabase = None

  def write_job(self, job_id: str, data: dict):
      # Always write to filesystem first
      with open(f"{self.jobs_dir}/{job_id}.json", "w") as f:
          json.dump(data, f)

      # Queue for sync if Supabase configured
      if self.supabase:
          self._queue_sync(f"jobs/{job_id}.json")

  def read_jobs(self) -> List[dict]:
      # API reads from Supabase (remote access)
      if self.supabase:
          return self.supabase.table("jobs").select("*").execute().data

      # Workers read from filesystem (local access)
      jobs = []
      for f in os.listdir(self.jobs_dir):
          if f.endswith(".json"):
              with open(f"{self.jobs_dir}/{f}") as file:
                  jobs.append(json.load(file))
      return jobs
```

#### 3.2.3 API Layer (Deployed to Vercel)

```
# api/main.py
from fastapi import FastAPI
from dr_exp import JobDB

app = FastAPI()

# API always uses Supabase for remote access
db = JobDB(
  experiment_name=os.getenv("EXPERIMENT_NAME"),
  supabase_url=os.getenv("SUPABASE_URL")
)

@app.get("/api/jobs")
async def list_jobs():
  return db.read_jobs()

@app.get("/api/metrics/{job_id}")
async def get_metrics(job_id: str):
  # Fetch from Supabase storage
  return db.get_metrics(job_id)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
  # Subscribe to Supabase realtime updates
  await websocket.accept()
  async for update in db.subscribe_updates():
      await websocket.send_json(update)
```

### 3.3 Deployment Configuration

```
# vercel.json
{
"functions": {
  "api/main.py": {
    "runtime": "python3.9"
  }
},
"env": {
  "EXPERIMENT_NAME": "@experiment_name",
  "SUPABASE_URL": "@supabase_url",
  "SUPABASE_KEY": "@supabase_key"
}
}
```

## 4. Implementation Plan

### Phase 1: Clean Slate (Week 1)

1. Create new branch: architecture-redesign
2. Delete all legacy code:
    - Remove LocalJobDB, SupabaseJobDB classes
    - Remove mode selection logic
    - Remove complex factory patterns
3. Implement single JobDB class with clear filesystem operations
4. Test basic read/write operations

### Phase 2: Worker Integration (Week 2)

1. Add sync thread to base Worker class
2. Implement sync queue with rate limiting
3. Add progress tracking for uploads
4. Test with dummy training loop

### Phase 3: Supabase Integration (Week 3)

1. Create Supabase schema:
```
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    experiment_name TEXT,
    status TEXT,
    config JSONB,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE TABLE sync_status (
    local_path TEXT PRIMARY KEY,
    remote_path TEXT,
    synced_at TIMESTAMPTZ,
    sync_status TEXT
);
```
2. Implement upload methods
3. Add retry logic with exponential backoff
4. Test end-to-end sync

### Phase 4: API Deployment (Week 4)

1. Create minimal FastAPI app
2. Deploy to Vercel:
```
vercel deploy --prod
```
3. Configure environment variables
4. Test remote access

### Phase 5: Frontend Updates (Week 5)

1. Update API client to use new endpoints
2. Add real-time WebSocket support
3. Implement metric plotting
4. Add log viewer

### Phase 6: Migration Tools (Week 6)

1. Create migration script:
```
def migrate_experiment(old_path: str, experiment_name: str):
  # Copy data to new structure
  # Upload to Supabase
  # Verify integrity
  # Delete old data
```
2. Document migration process
3. Test with real experiments

## 5. Clean Codebase Principles

### 5.1 No Hidden Behaviors

- Storage location is always explicit
- Sync status is visible in .sync_status.json
- No automatic caching
- Clear error messages

### 5.2 Single Source of Truth

- /scratch is always authoritative
- Supabase is always derived
- Conflicts resolved by re-syncing from /scratch
- No bidirectional sync

### 5.3 Fail Fast

- Assert all assumptions
- No silent failures
- Clear error propagation
- Explicit retry policies

### 5.4 Simple Configuration

```
# Worker configuration
config = {
  "experiment_name": "resnet_hparam_search",
  "sync_enabled": True,
  "sync_interval": 300,  # seconds
  "rate_limit": 10,      # files per sync
}
```

# API configuration (environment variables)
```
EXPERIMENT_NAME=resnet_hparam_search
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=xxx
```

## 6. Success Metrics

- Zero SSH sessions for monitoring during travel
- < 5 minute lag between training metrics and frontend display
- < 100 MB/day cluster egress for typical experiment
- Single command deployment for API updates
- No legacy code remaining in codebase

### 7. Future Enhancements

Once the clean architecture is established:

1. Multi-experiment support: Switch between experiments in UI
2. Collaborative features: Share experiment links
3. Advanced analytics: SQL queries across all experiments
4. Mobile app: Native iOS/Android for monitoring
5. Alerts: Push notifications for job completion/failure

This architecture provides a solid foundation for these enhancements without requiring fundamental changes.
