# Priority System Documentation

## Overview

The dr_exp experiment manager includes a comprehensive priority-based job scheduling system that allows researchers to manage experiment execution order, handle urgent deadlines, and ensure critical jobs run immediately when needed.

## Architecture

### Core Components

1. **Priority Queue**: Jobs are ordered by priority (0-1000, higher = more urgent) with tie-breaking by submission time
2. **Job Reservations**: Mechanism to reserve jobs for specific workers with timeout support
3. **Priority Classes**: Predefined priority ranges for different job types
4. **Priority Management**: CLI tools for adjusting job priorities during execution

### Priority Classes

The system defines five priority classes to help organize experiment priorities:

| Class | Range | Description | Use Cases |
|-------|-------|-------------|-----------|
| **SYSTEM** | 900-1000 | Critical system operations | System maintenance, urgent bug fixes |
| **URGENT** | 700-899 | Deadline-driven experiments | Conference deadlines, "run one" jobs |
| **HIGH** | 400-699 | Important experiments | Key research experiments, validation runs |
| **NORMAL** | 100-399 | Regular experiments | Standard hyperparameter sweeps, exploration |
| **LOW** | 0-99 | Background jobs | Large parameter sweeps, long-running studies |

## API Reference

### BaseJobDB Interface

All job database implementations support the following priority-related methods:

#### Priority Management

```python
def update_job_priority(
    self, 
    job_id: str, 
    new_priority: int, 
    reason: Optional[str] = None
) -> Dict[str, Any]:
    """Update job priority with audit trail."""

def boost_job_priority(
    self, 
    job_id: str, 
    boost_amount: int = 100
) -> Dict[str, Any]:
    """Boost job priority by specified amount."""

def list_jobs_by_priority(
    self,
    status_filter: Optional[List[str]] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """List jobs ordered by priority (highest first)."""
```

#### Job Reservations

```python
def add_reserved_job(
    self,
    job_config: Dict[str, Any],
    sweep_config_id: str,
    reserved_for_worker: str,
    reservation_timeout: Optional[int] = 300,
    priority: int = 100,
    status: str = "queued",
) -> Dict[str, Any]:
    """Add job reserved for specific worker."""

def claim_job(
    self, 
    worker_id: Optional[str] = None,
    respect_reservations: bool = True
) -> Optional[Dict[str, Any]]:
    """Claim job respecting priority and reservations."""
```

### Priority Utility Functions

Located in `dr_exp.utils.priority`:

```python
from dr_exp.utils.priority import (
    PriorityClass,
    calculate_age_boost,
    calculate_failure_penalty,
    get_priority_for_class
)

# Get priority range for class
urgent_min, urgent_max = PriorityClass.URGENT.value

# Calculate priority adjustments
age_boost = calculate_age_boost(days_old=7, max_boost=100)
failure_penalty = calculate_failure_penalty(failure_count=2, max_penalty=200)
```

## CLI Usage

### Job Submission with Priority

```bash
# Submit jobs with specific priority
uv run python scripts/upload_configs.py \
    --priority 800 \
    --sweep "model=resnet,vit optim=adam,sgd" \
    --description "Urgent deadline experiment"

# Default priority (100) if not specified
uv run python scripts/upload_configs.py \
    --sweep "lr=0.001,0.01,0.1"
```

### Priority Management Commands

```bash
# List jobs by priority
uv run python -m scripts.manager_cli list-jobs \
    --status queued \
    --limit 20

# Boost job priority
uv run python -m scripts.manager_cli boost-priority <job_id> \
    --amount 200

# Set exact priority
uv run python -m scripts.manager_cli set-priority <job_id> 900 \
    --reason "Conference deadline in 2 days"

# List all management commands
uv run python -m scripts.manager_cli --help
```

### Run One Functionality

The "run one" feature allows immediate execution of a single job with high priority:

```bash
# Basic run one with auto-generated config
uv run python -m scripts.manager_cli run-one \
    --overrides "model=resnet lr=0.001" \
    --priority 850

# Run one with custom configuration
uv run python -m scripts.manager_cli run-one \
    --config-name my_experiment.yaml \
    --overrides "epochs=100 batch_size=32" \
    --priority 900 \
    --reservation-timeout 600

# Run one with specific work directory
uv run python scripts/run_one.py \
    --overrides "model=vit" \
    --work-dir /tmp/urgent_experiment \
    --worker-id urgent_worker_1
```

## Implementation Details

### Priority-Aware Job Claiming

The `claim_job()` method implements priority-aware job selection:

1. **Job Collection**: Collect all queued jobs
2. **Reservation Check**: Filter based on worker reservations if `respect_reservations=True`
3. **Priority Sort**: Sort by priority (descending), then by age (ascending)
4. **Atomic Claim**: Use file locking for thread-safe job claiming

### Reservation System

Job reservations allow workers to "claim" specific jobs:

- **Timeout Support**: Reservations expire automatically if not claimed
- **Priority Integration**: Reserved jobs still respect priority ordering
- **Exclusive Access**: Only the designated worker can claim reserved jobs
- **Graceful Degradation**: Expired reservations are automatically cleared

### Audit Trail

All priority changes are logged with:
- Timestamp of the change
- Old and new priority values
- Reason for the change (if provided)
- Change type (manual update vs automatic boost)

## Best Practices

### Priority Assignment Guidelines

1. **Use Appropriate Classes**: Follow the priority class guidelines for consistent behavior
2. **Provide Reasons**: Include reasons when manually adjusting priorities for audit purposes
3. **Avoid Extreme Values**: Prefer mid-range values within each class rather than boundaries
4. **Monitor Queue**: Use `list-jobs` regularly to understand queue status

### Run One Usage

1. **Reserve for Urgent Work**: Use run-one for truly urgent experiments that can't wait
2. **Simple Configurations**: Keep overrides simple since run-one expects exactly one configuration
3. **Appropriate Priority**: Use URGENT class (700-899) for run-one jobs
4. **Resource Awareness**: Ensure adequate resources are available before using run-one

### Queue Management

1. **Regular Monitoring**: Check queue status with `list-jobs` to understand workload
2. **Priority Adjustments**: Boost priorities for experiments approaching deadlines
3. **Background Jobs**: Use LOW priority for large sweeps that can run opportunistically
4. **System Maintenance**: Use SYSTEM priority for critical infrastructure work

## Troubleshooting

### Common Issues

**Job not running despite high priority:**
- Check if job is reserved for a different worker
- Verify job status is "queued" and not "running" or "failed"
- Ensure worker processes are active and claiming jobs

**Run one fails with "exactly 1 config" error:**
- Simplify overrides to generate only one configuration
- Avoid comma-separated values in overrides for run-one
- Use upload-configs for multi-configuration sweeps instead

**Priority changes not taking effect:**
- Verify job ID is correct
- Check that job exists and is not already completed
- Ensure database client has write permissions

### Debugging Commands

```bash
# Check specific job details
uv run python -c "
from dr_exp.utils.jobdb_factory import get_supabase_client
client = get_supabase_client()
job = client.get_job_details('<job_id>')
print(f'Priority: {job.get(\"priority\", \"N/A\")}')
print(f'Status: {job.get(\"status\", \"N/A\")}')
print(f'Reserved for: {job.get(\"reserved_for_worker\", \"None\")}')
"

# List priority changes for job
uv run python -c "
from dr_exp.utils.jobdb_factory import get_supabase_client
client = get_supabase_client()
job = client.get_job_details('<job_id>')
changes = job.get('priority_changes', [])
for change in changes:
    print(f'{change[\"timestamp\"]}: {change[\"old_priority\"]} -> {change[\"new_priority\"]} ({change.get(\"reason\", \"No reason\")})')
"
```

## Migration and Compatibility

### Upgrading from Non-Priority Systems

Existing jobs without priority fields will automatically receive:
- Default priority of 100 (NORMAL class)
- Priority boost count of 0
- Empty priority changes history

### Database Schema Updates

The priority system adds these fields to job records:
- `priority` (integer, default 100)
- `priority_boost_count` (integer, default 0)
- `priority_changes` (JSON array of change records)
- `reserved_for_worker` (string, optional)
- `reservation_expires_at` (timestamp, optional)

## Performance Considerations

### Scalability

- Priority sorting is efficient for typical job queue sizes (< 10,000 jobs)
- File locking ensures thread-safety but may create contention with many workers
- Consider batching priority updates for bulk operations

### Resource Usage

- Priority calculation is O(n log n) where n is the number of queued jobs
- Reservation checking adds minimal overhead
- Audit trail storage grows linearly with priority changes

## Future Enhancements

Potential improvements for the priority system:

1. **Dynamic Priority Adjustment**: Automatic priority boosts based on job age or failure count
2. **Priority Policies**: Configurable rules for automatic priority management
3. **Resource-Aware Priorities**: Priority adjustments based on resource availability
4. **Web UI Integration**: Graphical priority management in the React frontend
5. **Notification System**: Alerts when high-priority jobs are waiting too long