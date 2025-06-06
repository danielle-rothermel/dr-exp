# Priority System Implementation Summary

This document provides a quick overview of the priority system implementation in dr_exp.

## Quick Start

### Submit jobs with priority
```bash
# High priority for urgent experiments
uv run python scripts/upload_configs.py --priority 800 --sweep "model=resnet,vit"

# Normal priority (default)
uv run python scripts/upload_configs.py --sweep "lr=0.001,0.01"
```

### Monitor queue
```bash
# List top priority queued jobs
uv run python -m scripts.manager_cli list-jobs --status queued --limit 10
```

### Manage priorities
```bash
# Boost job priority
uv run python -m scripts.manager_cli boost-priority <job_id> --amount 200

# Set exact priority
uv run python -m scripts.manager_cli set-priority <job_id> 900 --reason "Deadline"
```

### Run urgent job immediately
```bash
# Reserve and run single job with high priority
uv run python -m scripts.manager_cli run-one --overrides "model=resnet lr=0.001" --priority 850
```

## Priority Classes

| Class | Range | Usage |
|-------|-------|-------|
| SYSTEM | 900-1000 | Critical maintenance |
| URGENT | 700-899 | Deadlines, run-one jobs |
| HIGH | 400-699 | Important experiments |
| NORMAL | 100-399 | Regular work (default) |
| LOW | 0-99 | Background jobs |

## Key Features Implemented

✅ **Priority-based job queue** - Jobs run in priority order  
✅ **Job reservations** - Reserve jobs for specific workers  
✅ **"Run one" functionality** - Immediate execution bypassing queue  
✅ **Priority management CLI** - Boost, set, and list by priority  
✅ **Audit trails** - Track all priority changes with timestamps  
✅ **Comprehensive testing** - Full test coverage for new features  

## Documentation

- **Complete Guide**: `docs/priority_system.md`
- **CLI Reference**: `docs/manager_cli.md` 
- **API Details**: Code documentation in `src/dr_exp/`
- **Examples**: This document and README.md

## Implementation Files

### Core Components
- `src/dr_exp/job_db/base_job_db.py` - Abstract interface
- `src/dr_exp/job_db/local_job_db.py` - Local implementation
- `src/dr_exp/job_db/supabase_job_db.py` - Supabase implementation
- `src/dr_exp/utils/priority.py` - Priority utilities and classes

### CLI and Scripts
- `scripts/manager_cli.py` - Priority management commands
- `scripts/upload_configs.py` - Priority flag support
- `scripts/run_one.py` - Run one functionality
- `src/dr_exp/utils/config_upload.py` - Updated upload logic

### Worker Integration
- `src/dr_exp/manage/worker_logic.py` - Priority-aware job claiming
- `src/dr_exp/manage/manager_logic.py` - Queue monitoring

### Tests
- `tests/job_db/test_localdb_client.py` - Priority system tests
- `tests/job_db/test_base_job_db.py` - Interface compliance tests

## Migration Notes

Existing jobs automatically receive:
- Default priority: 100 (NORMAL class)
- Priority boost count: 0
- Empty priority change history

No database migration required for existing installations.

---

For detailed documentation, see `docs/priority_system.md`.