# CLI Flag Migration Plan: Environment Variables to Explicit Arguments

## Overview

This document outlines an aggressive migration from environment variable-based configuration to explicit CLI flag-based configuration. This approach completely eliminates configuration drift by making all configuration explicit and visible in command invocations.

## Goal

**Eliminate all environment variable dependencies** (`DR_EXP_BASE_PATH`, `EXPMGR_MODE`) and replace with required CLI arguments that must be specified on every command.

## New CLI Interface

### **Required Arguments (All Commands)**
```bash
--base-path /path/to/experiment/data    # Base directory for experiment data
--mode files_local|supabase_local|supabase_remote    # Database mode
```

### **Optional Arguments**
```bash
--storage-path /path/to/storage    # Storage directory (default: {base-path}/storage)
--supabase-url URL                 # Required for supabase modes
--supabase-key KEY                 # Required for supabase modes
```

### **Path Structure**
Jobs will be stored at: `{base-path}/job_data/`
Artifacts will be stored at: `{storage-path}/` (defaults to `{base-path}/storage/`)

## Implementation Details

### **1. BaseCommand Updates**

```python
class BaseCommand(ABC):
    def add_common_arguments(self, parser: ArgumentParser) -> None:
        """Add required configuration arguments to all commands."""
        parser.add_argument(
            "--base-path", 
            required=True,
            help="Base directory for experiment data (jobs stored in {base-path}/job_data)"
        )
        parser.add_argument(
            "--mode",
            required=True, 
            choices=["files_local", "supabase_local", "supabase_remote"],
            help="Database mode"
        )
        parser.add_argument(
            "--storage-path",
            help="Storage directory for artifacts (default: {base-path}/storage)"
        )
        parser.add_argument(
            "--supabase-url", 
            help="Supabase URL (required for supabase modes)"
        )
        parser.add_argument(
            "--supabase-key", 
            help="Supabase key (required for supabase modes)"
        )

    def create_system_from_args(self, args: Namespace) -> Factory:
        """Create system using CLI arguments instead of environment."""
        # Validate Supabase arguments based on mode
        if args.mode in ["supabase_local", "supabase_remote"]:
            if not args.supabase_url or not args.supabase_key:
                raise ValueError(f"--supabase-url and --supabase-key required for {args.mode} mode")
        
        # Default storage path if not provided
        storage_path = args.storage_path or os.path.join(args.base_path, "storage")
        
        # Build configuration from CLI arguments
        config = JobDBConfig(
            base_path=args.base_path,
            storage_path=storage_path,
            mode=args.mode,
            supabase_url=getattr(args, 'supabase_url', None),
            supabase_key=getattr(args, 'supabase_key', None),
        )
        
        system_config = SystemConfig(job_db_config=config)
        return create_system(system_config)
```

### **2. JobDBConfig Changes**

**Remove `from_env()` method completely:**

```python
@dataclass
class JobDBConfig:
    """Configuration for JobDB instances."""
    
    # Required fields - no defaults
    base_path: str
    mode: str
    
    # Optional fields with defaults
    storage_path: str = "./storage"
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None

    def __post_init__(self):
        """Validate configuration after initialization."""
        self.validate()

    def validate(self) -> None:
        """Validate configuration settings."""
        if self.mode in ["supabase_remote", "supabase_local"]:
            if not self.supabase_url or not self.supabase_key:
                raise ValueError(f"Supabase URL and Key required for {self.mode} mode")
            if not self.supabase_url.startswith(("http://", "https://")):
                raise ValueError("Invalid Supabase URL format")

        # Ensure paths are absolute for consistency
        self.base_path = os.path.abspath(self.base_path)
        self.storage_path = os.path.abspath(self.storage_path)
```

### **3. Command Updates Pattern**

Every CLI command must be updated to:

1. **Add common arguments in `add_arguments()`:**
```python
def add_arguments(self, parser: ArgumentParser) -> None:
    self.add_common_arguments(parser)  # Add --base-path, --mode, etc.
    # Command-specific arguments below
    parser.add_argument("--config-name", default="config.yaml")
    # ...
```

2. **Use CLI args in `run()`:**
```python
def run(self, args: Namespace) -> int:
    system = self.create_system_from_args(args)  # Use CLI args
    client = system.job_db
    # ... rest of implementation
```

## Breaking Changes and Migration

### **1. All CLI Commands** ❌

**Before:**
```bash
# Environment variables required
export DR_EXP_BASE_PATH="./logs"
export EXPMGR_MODE="files_local"

uvrp scripts/upload_configs.py --config-name decon_config --priority 150
uv run python scripts/manager_cli.py system run_worker dev_worker ./work
uv run python scripts/manager_cli.py job list_jobs
```

**After:**
```bash
# No environment variables needed - all explicit
uvrp scripts/upload_configs.py --base-path ./logs --mode files_local --config-name decon_config --priority 150
uv run python scripts/manager_cli.py --base-path ./logs --mode files_local system run_worker dev_worker ./work
uv run python scripts/manager_cli.py --base-path ./logs --mode files_local job list_jobs
```

### **2. All CLAUDE.md Workflow Examples** ❌

**Before:**
```bash
# Quick Dev Cycle (Supabase Local)
export EXPMGR_MODE=supabase_local
export DR_EXP_BASE_PATH="./logs"
supabase start

uvrp scripts/upload_configs.py --base-config-path configs --config-name decon_config --sweep "limit_train_batches=10 model=alexnet_cifar epochs=5" --priority 150
uv run python scripts/manager_cli.py system run_worker dev_worker ./work
```

**After:**
```bash
# Quick Dev Cycle (Supabase Local)
supabase start

uvrp scripts/upload_configs.py --base-path ./logs --mode supabase_local --base-config-path configs --config-name decon_config --sweep "limit_train_batches=10 model=alexnet_cifar epochs=5" --priority 150
uv run python scripts/manager_cli.py --base-path ./logs --mode supabase_local system run_worker dev_worker ./work
```

### **3. All Tests** ❌

**Before:**
```python
# Tests using environment variables
def test_something():
    config = JobDBConfig.from_env()
    system = create_system()
```

**After:**
```python
# Tests using explicit configuration
def test_something():
    config = JobDBConfig(
        base_path="./test_logs",
        mode="files_local",
        storage_path="./test_storage"
    )
    system_config = SystemConfig(job_db_config=config)
    system = create_system(system_config)
```

### **4. Factory Usage in Scripts** ❌

**Before:**
```python
# Scripts relying on environment
def main():
    system = create_system()  # Uses environment variables
```

**After:**
```python
# Scripts with explicit configuration
def main():
    parser = ArgumentParser()
    parser.add_argument("--base-path", required=True)
    parser.add_argument("--mode", required=True, choices=["files_local", "supabase_local", "supabase_remote"])
    args = parser.parse_args()
    
    config = JobDBConfig(base_path=args.base_path, mode=args.mode)
    system_config = SystemConfig(job_db_config=config)
    system = create_system(system_config)
```

### **5. API and Background Services** ❌

Any services that currently use `JobDBConfig.from_env()` will need to be updated to accept explicit configuration.

## Implementation Order

### **Phase 1: Core Infrastructure (Breaking Changes)**

1. **Update JobDBConfig**
   - Remove `from_env()` method completely
   - Make `base_path` and `mode` required constructor arguments
   - Update validation logic

2. **Update BaseCommand**
   - Add `add_common_arguments()` method
   - Add `create_system_from_args()` method
   - Add validation for Supabase arguments

3. **Update All CLI Commands (17 commands)**
   - `src/dr_exp/cli/commands/*.py` - Update all command classes
   - Add common arguments to each command's `add_arguments()`
   - Use `create_system_from_args()` in each command's `run()`

### **Phase 2: Fix All Breakages**

4. **Update All Tests**
   - Replace `JobDBConfig.from_env()` usage
   - Use explicit `JobDBConfig()` construction
   - Update test fixtures and conftest.py

5. **Update Scripts Directory**
   - `scripts/*.py` - Add CLI argument parsing
   - Replace environment variable dependencies

6. **Update Documentation**
   - `CLAUDE.md` - All workflow examples
   - `docs/` - Any configuration documentation
   - Help text and error messages

7. **Update API and Services**
   - `src/dr_exp/api/main.py` - FastAPI startup
   - Any background services or entry points

### **Phase 3: Validation and Cleanup**

8. **Integration Testing**
   - Test all documented workflows
   - Verify configuration consistency
   - Test error handling for missing arguments

9. **Documentation Updates**
   - Remove all environment variable references
   - Add comprehensive help text
   - Update troubleshooting guides

## Success Criteria

✅ **Zero environment variable dependencies** - No `DR_EXP_BASE_PATH` or `EXPMGR_MODE` required  
✅ **All CLI commands accept required flags** - `--base-path` and `--mode` on every command  
✅ **All CLAUDE.md examples work** - Every documented workflow functions with new syntax  
✅ **All tests pass** - Complete test suite using explicit configuration  
✅ **Configuration drift impossible** - No hidden environment state  
✅ **Self-documenting commands** - All configuration visible in command line  

## Benefits

1. **Eliminates Configuration Drift**: No hidden environment state means no mismatches
2. **Self-Documenting**: All configuration is visible in the command invocation
3. **Explicit Over Implicit**: Follows Python principles - no magical environment dependencies
4. **Debugging Friendly**: Easy to see exactly what configuration was used
5. **CI/CD Friendly**: No environment setup required, everything in command line
6. **Reproducible**: Commands can be copy-pasted and will work identically

## Risks and Mitigation

**Risk**: Commands become verbose with repeated `--base-path --mode` arguments  
**Mitigation**: Consider shell aliases or wrapper scripts for common patterns

**Risk**: Breaking all existing usage immediately  
**Mitigation**: This is intentional - forces immediate fixing of all configuration issues

**Risk**: Users forget required arguments  
**Mitigation**: Clear error messages with examples of correct usage

This aggressive migration completely eliminates the root cause of configuration drift by making all configuration explicit and required.