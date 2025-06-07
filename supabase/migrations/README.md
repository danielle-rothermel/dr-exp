# Database Migrations

This directory contains SQL migration files that define the database schema for the experiment management system.

## Migration Files

### `0001_initial_schema.sql`
**Purpose:** Establishes the core database schema with basic tables and relationships.

**Tables Created:**
- `sweep_config_clusters`: High-level groupings of related experiment sweeps
- `sweep_configs`: Individual Hydra-resolved configuration instances  
- `jobs`: Main table tracking training jobs with status, metrics, and artifacts
- `metrics`: Per-epoch/step metric logging for real-time monitoring
- `errors`: Structured error logging and failure tracking
- `failures`: Retry audit log for repeated job failures

**Key Features:**
- PostgreSQL UUID primary keys with auto-generation
- Foreign key relationships with appropriate cascade/restrict rules
- Comprehensive indexing for query performance
- Detailed column comments for documentation

### `0002_add_priority_and_reservations.sql`
**Purpose:** Adds priority-based job scheduling and worker reservation system.

**Enhancements:**
- `priority` column (0-1000 range) for job queue ordering
- `reserved_for_worker` and `reservation_expires_at` for worker-specific jobs
- `created_at` timestamp for proper job ordering
- Updated status constraints to include 'killed' status
- Performance indexes for priority-based queries

**PostgreSQL Functions:**
- `claim_next_job(worker_id_input TEXT)`: Atomic job claiming with priority logic
  - Respects reservations and expiration times
  - Orders by priority (high to low), then creation time (old to new)
  - Uses `FOR UPDATE SKIP LOCKED` for safe concurrent access

### `0003_create_storage_bucket.sql`
**Purpose:** Creates the Supabase Storage bucket for experiment artifacts.

**Storage Setup:**
- `experiment-artifacts` bucket for storing metrics, checkpoints, and results
- 100MB file size limit with common MIME types allowed
- Proper permissions for service role access

## Usage

### Local Development
```bash
# Start local Supabase (automatically applies migrations)
supabase start

# Reset database and reapply all migrations
supabase db reset
```

### Adding New Migrations
```bash
# Create a new migration file
supabase migration new my_new_feature

# Edit the generated file in supabase/migrations/
# Apply with:
supabase db reset
```

### Production Deployment
Migrations are applied automatically when deploying to production Supabase instances through the Supabase CLI or dashboard.

## Schema Design Principles

1. **Append-Only Operations:** Jobs, metrics, and errors are designed for append-only workflows
2. **Atomic Job Claiming:** Worker coordination uses PostgreSQL functions for race-condition-free job assignment
3. **Priority Scheduling:** Higher priority jobs (0-1000) are processed first, with tie-breaking by creation time
4. **Worker Reservations:** Jobs can be reserved for specific workers with automatic timeout handling
5. **Audit Trails:** All important state changes include timestamps and reasoning for debugging
6. **Performance:** Strategic indexing on frequently queried columns (status, priority, worker assignment)

## Testing

The migration system is tested in both local and production environments:
- Unit tests verify table structure and constraints
- Integration tests validate job claiming logic and priority ordering
- Performance tests ensure indexes are effective for large job queues

## Troubleshooting

**Migration Errors:**
- Check Docker is running for local Supabase
- Verify no syntax errors in SQL files
- Use `supabase db reset` to restart from clean state

**Performance Issues:**
- Review query plans for job claiming operations
- Monitor index usage with PostgreSQL statistics
- Consider additional indexes for specific query patterns
