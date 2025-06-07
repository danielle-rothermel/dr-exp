# Architecture Overview

## Executive Summary

The Experiment Manager (`dr_exp`) has undergone a comprehensive refactoring to achieve a streamlined architecture with clean separation of concerns. The system now eliminates mixed responsibilities through abstract interface methods, improving maintainability while preserving all existing functionality.

## Core Architectural Principles

### 1. Abstract Interface Methods
The manager coordinates workers using only abstract methods from `BaseJobDB`, eliminating database-specific code paths:

```python
# Manager uses abstract methods only
stale_jobs = self.job_db.get_stale_jobs(max_age_seconds)
self.job_db.mark_jobs_failed(job_ids, reason="worker_lost")
has_work = self.job_db.has_queued_jobs()
```

### 2. Separation of Concerns
- **Manager**: Pure coordination logic, no database implementation details
- **Worker**: Job execution with improved error handling
- **ProcessManager**: Multiprocessing abstraction
- **Factory**: Consistent system integration

### 3. Factory Pattern
Unified system creation ensures consistent configuration and shared instances:

```python
system = create_system(config)
manager = system.create_manager()
worker_status = system.run_worker(worker_id="dev_worker")
```

## System Components

### Database Layer (`src/dr_exp/job_db/`)

#### BaseJobDB (Abstract Interface)
Defines streamlined methods for all job operations:

```python
@abstractmethod
def list_running_jobs(self) -> List[Dict[str, Any]]: ...
def get_stale_jobs(self, max_age_seconds: int) -> List[StaleJobInfo]: ...
def mark_jobs_failed(self, job_ids: List[str], reason: str) -> Dict[str, bool]: ...
def has_queued_jobs(self) -> bool: ...
def get_queue_summary(self, limit: int = 5) -> List[Dict[str, Any]]: ...
```

#### LocalJobDB
- JSON file-based storage for development
- Fast, simple, no external dependencies
- Implements all abstract methods efficiently

#### SupabaseJobDB  
- PostgreSQL backend for production
- Real-time features and robust storage
- Atomic job claiming with SQL functions
- Batch operations for performance

#### JobDBConfig
- Unified configuration system
- Environment-aware defaults
- Supports all database modes seamlessly

### Manager/Worker System (`src/dr_exp/manage/`)

#### Manager
Coordinates workers using only abstract interface methods:

**Key Responsibilities:**
- Launch workers via ProcessManager
- Monitor job health using abstract methods
- Handle idle timeout and shutdown
- Log system status

**Core Methods:**
```python
def start_workers(self) -> None: ...
def run(self) -> None: ...  # Main event loop
def check_stale_jobs(self) -> None: ...
def check_idle_timeout(self) -> None: ...
```

#### Worker
Redesigned with improved separation of concerns:

**Components:**
- `HeartbeatManager`: Background heartbeat thread
- `JobExecutor`: Training execution with error handling
- `managed_work_directory`: Temporary directory management

**Enhanced Features:**
- Comprehensive exception capture
- Structured error logging with stack traces
- Automatic cleanup on success/failure
- Proper artifact uploading regardless of outcome

#### ProcessManager
Abstracts multiprocessing from manager logic:

```python
class BaseProcessManager(ABC):
    @abstractmethod
    def launch_worker(self, worker_id: str, gpu_id: str, work_dir: str) -> bool: ...
    def stop_all_workers(self) -> None: ...
    def get_worker_status(self) -> Dict[str, Dict[str, Any]]: ...
```

**Implementations:**
- `ProcessManager`: Real multiprocessing
- `MockProcessManager`: Testing support

### Factory System (`src/dr_exp/utils/factory.py`)

#### SystemConfig
Unified configuration for all components:

```python
@dataclass
class SystemConfig:
    # Database configuration
    job_db_config: Optional[JobDBConfig] = None
    
    # Manager configuration  
    gpus: Optional[List[str]] = None
    workers_per_gpu: int = 1
    heartbeat_timeout: int = 60
    idle_timeout_mins: int = 30
    
    # Worker configuration
    max_claim_attempts: int = 5
    worker_heartbeat_interval: float = 5.0
```

#### Factory
Creates properly integrated system components:

```python
class Factory:
    def create_manager(self) -> Manager: ...
    def run_worker(self, worker_id: str) -> str: ...
    def get_system_status(self) -> dict: ...
```

## Key Improvements

### 1. Eliminated Mixed Responsibilities
**Before:** Manager contained database-specific code for different backends
**After:** Manager uses only abstract interface methods

### 2. Enhanced Error Handling
- Structured exception capture and logging
- Comprehensive stack trace recording
- Automatic recovery from worker failures
- Graceful degradation on resource issues

### 3. Improved Testing
- Clean separation enables isolated unit testing
- Mock implementations for all major components
- Integration tests demonstrate end-to-end workflows
- 172+ tests with comprehensive coverage

### 4. Better Resource Management
- Isolated worker environments
- Proper cleanup on shutdown
- Efficient batch operations
- Minimal monitoring overhead

## Data Flow

### Job Execution Flow
1. **Job Creation**: Configurations uploaded via CLI
2. **Job Claiming**: Workers claim jobs by priority
3. **Execution**: Training runs with heartbeat monitoring
4. **Monitoring**: Manager detects stale jobs and recovers
5. **Completion**: Results uploaded and job finalized

### Health Monitoring Flow
1. **Heartbeats**: Workers send regular status updates
2. **Detection**: Manager identifies stale jobs via abstract methods
3. **Recovery**: Failed jobs marked, workers restarted
4. **Cleanup**: Resources freed, system continues

### Priority System Flow
1. **Prioritization**: Jobs queued with priority levels (0-1000)
2. **Claiming**: Workers claim highest priority jobs first
3. **Monitoring**: Manager logs queue status during idle periods
4. **Management**: CLI tools allow priority adjustments

## Environment Modes

### Files Local (`EXPMGR_MODE=files_local`)
- JSON file storage in local directories
- No external dependencies
- Perfect for development and testing
- Fast startup and teardown

### Supabase Local (`EXPMGR_MODE=supabase_local`)
- Local PostgreSQL with full Supabase features
- Real-time updates and WebSocket support
- Comprehensive storage capabilities
- Requires Docker but provides realistic environment

### Supabase Remote (`EXPMGR_MODE=supabase_remote`)
- Cloud PostgreSQL for production
- Scalable storage and compute
- Real-time collaboration features
- Requires Supabase account

## Command Line Interface

### System Management
```bash
# Create and run system
uv run python scripts/run_manager.py --gpus-per-node 2 --workers-per-gpu 2
uv run python scripts/run_worker.py --worker-id dev_worker

# Upload experiments
uv run python scripts/manager_cli.py upload-configs --sweep "model=resnet,vit"

# Monitor and control
uv run python scripts/manager_cli.py list-jobs --status queued
uv run python scripts/manager_cli.py boost-priority <job_id> --amount 200
```

### Development Commands
```bash
# Start local environment
supabase start
export EXPMGR_MODE=supabase_local
uv run uvicorn dr_exp.api.main:app --reload

# Run tests
uv run pytest  # 172+ tests pass
uv run pytest tests/manage/test_integration.py  # Integration tests
```

## Integration Points

### FastAPI Backend
- Comprehensive REST API with authentication and role-based access control
- Real-time WebSocket communication for job status updates
- Advanced job querying with pagination, filtering, and sorting
- Priority management endpoints for job queue control
- System monitoring with health checks and metrics
- Request logging and performance monitoring
- API versioning with deprecation management
- No direct communication with manager/workers (database-mediated)

### React Frontend
- Real-time job monitoring with WebSocket integration
- Advanced job filtering, sorting, and pagination
- Priority-aware job display and queue management
- Authenticated job control (kill, requeue, priority management)
- System health monitoring and API status display
- Role-based access control (admin vs reader permissions)

### SLURM Integration
- Batch job submission via `sbatch`
- GPU discovery and resource allocation
- Environment variable configuration
- Graceful shutdown handling

## Performance Characteristics

### Efficiency Improvements
- **Batch Operations**: Multiple jobs processed in single database calls
- **Lightweight Monitoring**: Efficient queries using abstract methods
- **Minimal Overhead**: Streamlined heartbeat mechanism
- **Resource Isolation**: Clean worker environment separation

### Scalability Features
- **Configurable Workers**: Multiple workers per GPU
- **Priority Queuing**: Efficient job ordering
- **Automatic Recovery**: Self-healing from failures
- **Storage Abstraction**: Local or cloud storage options

## Future Extensibility

The streamlined architecture enables easy extension:

1. **New Database Backends**: Implement `BaseJobDB` interface
2. **Custom Workers**: Extend worker components for specialized tasks
3. **Advanced Scheduling**: Add new priority algorithms
4. **Monitoring Integration**: Plugin architecture for external monitoring

This refactored architecture provides a solid foundation for scaling experiments while maintaining clean code organization and comprehensive testing coverage.