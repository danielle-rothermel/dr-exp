# Step 3.1: Database Schema

## Goal (1 sentence)
Create Supabase database schema with tables for experiments, jobs, and sync status, plus storage bucket configuration.

## Prerequisites
- [ ] Phase 2 complete with all tests passing
- [ ] Supabase CLI installed: `brew install supabase/tap/supabase`
- [ ] Supabase project created (or use local)

## Implementation

### 1. Create supabase/config.toml
```toml
# Supabase project configuration
[project]
id = "local"

[api]
enabled = true
port = 54321
schemas = ["public"]

[db]
port = 54322
major_version = 15

[studio]
enabled = true
port = 54323

[storage]
enabled = true

[auth]
enabled = true
```

### 2. Create supabase/migrations/001_initial_schema.sql
```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Experiments table
CREATE TABLE experiments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    experiment_name TEXT NOT NULL,
    base_path TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    UNIQUE(base_path, experiment_name)
);

-- Jobs table
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    config JSONB NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    status TEXT NOT NULL DEFAULT 'queued',
    worker_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    last_heartbeat TIMESTAMP WITH TIME ZONE,
    attempts INTEGER DEFAULT 0,
    error TEXT,
    final_metrics JSONB,
    reserved_for TEXT,
    reservation_time TIMESTAMP WITH TIME ZONE,
    priority_boosted BOOLEAN DEFAULT FALSE,
    recovery_count INTEGER DEFAULT 0,
    last_recovery TIMESTAMP WITH TIME ZONE,
    CHECK (priority >= 0 AND priority <= 1000),
    CHECK (status IN ('queued', 'running', 'completed', 'failed', 'killed'))
);

-- Indexes for job queries
CREATE INDEX idx_jobs_experiment_status ON jobs(experiment_id, status);
CREATE INDEX idx_jobs_experiment_priority ON jobs(experiment_id, priority DESC, created_at ASC) 
    WHERE status = 'queued';
CREATE INDEX idx_jobs_heartbeat ON jobs(last_heartbeat) 
    WHERE status = 'running';

-- Sync status table
CREATE TABLE sync_status (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    checksum TEXT,
    size_bytes BIGINT,
    storage_url TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    attempts INTEGER DEFAULT 0,
    last_attempt TIMESTAMP WITH TIME ZONE,
    error TEXT,
    metadata JSONB DEFAULT '{}',
    CHECK (status IN ('pending', 'uploading', 'completed', 'failed'))
);

-- Index for sync queries
CREATE INDEX idx_sync_status_job ON sync_status(job_id);
CREATE INDEX idx_sync_pending ON sync_status(status, created_at) 
    WHERE status = 'pending';

-- Update timestamp function
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_experiments_updated_at BEFORE UPDATE ON experiments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_jobs_updated_at BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_sync_status_updated_at BEFORE UPDATE ON sync_status
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Views for common queries
CREATE VIEW job_queue AS
SELECT 
    j.id,
    j.experiment_id,
    e.experiment_name,
    j.priority,
    j.created_at,
    j.config->>'_target_' as target,
    j.reserved_for,
    ROW_NUMBER() OVER (
        PARTITION BY j.experiment_id 
        ORDER BY j.priority DESC, j.created_at ASC
    ) as queue_position
FROM jobs j
JOIN experiments e ON j.experiment_id = e.id
WHERE j.status = 'queued';

CREATE VIEW experiment_stats AS
SELECT 
    e.id,
    e.experiment_name,
    e.created_at,
    COUNT(j.id) as total_jobs,
    COUNT(j.id) FILTER (WHERE j.status = 'queued') as queued_jobs,
    COUNT(j.id) FILTER (WHERE j.status = 'running') as running_jobs,
    COUNT(j.id) FILTER (WHERE j.status = 'completed') as completed_jobs,
    COUNT(j.id) FILTER (WHERE j.status = 'failed') as failed_jobs,
    COUNT(j.id) FILTER (WHERE j.status = 'killed') as killed_jobs,
    MAX(j.updated_at) as last_activity
FROM experiments e
LEFT JOIN jobs j ON e.id = j.experiment_id
GROUP BY e.id, e.experiment_name, e.created_at;

-- Row Level Security (RLS)
ALTER TABLE experiments ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_status ENABLE ROW LEVEL SECURITY;

-- Policies (allow all for service role)
CREATE POLICY "Service role has full access to experiments" ON experiments
    FOR ALL USING (true);

CREATE POLICY "Service role has full access to jobs" ON jobs
    FOR ALL USING (true);

CREATE POLICY "Service role has full access to sync_status" ON sync_status
    FOR ALL USING (true);
```

### 3. Create supabase/migrations/002_storage_bucket.sql
```sql
-- Create storage bucket for experiment artifacts
INSERT INTO storage.buckets (id, name, public, avif_autodetection, allowed_mime_types)
VALUES (
    'experiments',
    'experiments', 
    false,  -- Private bucket
    false,
    ARRAY[
        'application/json',
        'text/plain',
        'application/octet-stream',
        'application/x-python-pickle',  -- For PyTorch models
        'application/x-hdf5',           -- For HDF5 files
        'application/gzip',
        'application/zip'
    ]
);

-- Storage policies for service role
CREATE POLICY "Service role can upload to experiments" ON storage.objects
    FOR INSERT WITH CHECK (bucket_id = 'experiments');

CREATE POLICY "Service role can read experiments" ON storage.objects
    FOR SELECT USING (bucket_id = 'experiments');

CREATE POLICY "Service role can update experiments" ON storage.objects
    FOR UPDATE USING (bucket_id = 'experiments');

CREATE POLICY "Service role can delete from experiments" ON storage.objects
    FOR DELETE USING (bucket_id = 'experiments');
```

### 4. Create supabase/seed.sql
```sql
-- Optional: Seed data for testing
INSERT INTO experiments (experiment_name, base_path, metadata) VALUES
    ('test_experiment', '/tmp/test', '{"description": "Test experiment for development"}');
```

### 5. Create tests/implementation/test_step_3_1.py
```python
"""Test database schema setup."""
import subprocess
import os
import time
import pytest
from pathlib import Path


def test_local_supabase():
    """Test local Supabase setup."""
    # Check if Supabase is installed
    result = subprocess.run(['supabase', '--version'], capture_output=True, text=True)
    assert result.returncode == 0, "Supabase CLI not installed"
    print(f"Supabase version: {result.stdout.strip()}")
    
    # Start Supabase (if not already running)
    print("Starting local Supabase...")
    result = subprocess.run(['supabase', 'start'], capture_output=True, text=True)
    if result.returncode != 0 and "is already running" not in result.stderr:
        print(f"Error starting Supabase: {result.stderr}")
        assert False, "Failed to start Supabase"
    
    # Wait for services to be ready
    time.sleep(2)
    
    # Get status
    result = subprocess.run(['supabase', 'status'], capture_output=True, text=True)
    assert result.returncode == 0
    print("Supabase status:")
    print(result.stdout)
    
    # Extract connection info
    lines = result.stdout.strip().split('\n')
    for line in lines:
        if 'API URL:' in line:
            api_url = line.split(':', 1)[1].strip()
        elif 'anon key:' in line:
            anon_key = line.split(':', 1)[1].strip()
        elif 'service_role key:' in line:
            service_key = line.split(':', 1)[1].strip()
    
    print(f"\nConnection info:")
    print(f"API URL: {api_url}")
    print(f"Service key: {service_key[:20]}...")
    
    
    return api_url, service_key


def test_database_schema():
    """Test database schema with psycopg2."""
    try:
        import psycopg2
    except ImportError:
        subprocess.run(['uv', 'add', 'psycopg2-binary'], check=True)
        import psycopg2
    
    # Connect to local database
    conn = psycopg2.connect(
        host="localhost",
        port=54322,
        database="postgres",
        user="postgres",
        password="postgres"
    )
    
    try:
        cur = conn.cursor()
        
        # Check tables exist
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        
        tables = [row[0] for row in cur.fetchall()]
        print(f"\nTables: {tables}")
        
        required_tables = ['experiments', 'jobs', 'sync_status']
        for table in required_tables:
            assert table in tables, f"Missing table: {table}"
        
        # Check views
        cur.execute("""
            SELECT table_name 
            FROM information_schema.views 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        
        views = [row[0] for row in cur.fetchall()]
        print(f"Views: {views}")
        
        assert 'job_queue' in views
        assert 'experiment_stats' in views
        
        # Check indexes
        cur.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND tablename = 'jobs'
            ORDER BY indexname;
        """)
        
        indexes = [row[0] for row in cur.fetchall()]
        print(f"Job indexes: {indexes}")
        
        assert any('priority' in idx for idx in indexes)
        assert any('heartbeat' in idx for idx in indexes)
        
        # Test inserting data
        cur.execute("""
            INSERT INTO experiments (experiment_name, base_path) 
            VALUES (%s, %s) 
            RETURNING id;
        """, ('schema_test', '/tmp/schema_test'))
        
        exp_id = cur.fetchone()[0]
        
        # Insert a job
        cur.execute("""
            INSERT INTO jobs (id, experiment_id, config, priority, status)
            VALUES (gen_random_uuid(), %s, %s, %s, %s)
            RETURNING id;
        """, (exp_id, '{"_target_": "test.train"}', 500, 'queued'))
        
        job_id = cur.fetchone()[0]
        
        # Test job queue view
        cur.execute("""
            SELECT * FROM job_queue 
            WHERE experiment_id = %s;
        """, (exp_id,))
        
        queue_row = cur.fetchone()
        assert queue_row is not None
        print(f"Job queue position: {queue_row[-1]}")
        
        # Test experiment stats view
        cur.execute("""
            SELECT * FROM experiment_stats 
            WHERE id = %s;
        """, (exp_id,))
        
        stats = cur.fetchone()
        assert stats is not None
        total_jobs_idx = 3  # Adjust based on actual column order
        assert stats[total_jobs_idx] == 1  # 1 total job
        
        conn.commit()
        
    finally:
        cur.close()
        conn.close()


def test_storage_bucket():
    """Test storage bucket configuration."""
    import psycopg2
    
    conn = psycopg2.connect(
        host="localhost",
        port=54322,
        database="postgres",
        user="postgres",
        password="postgres"
    )
    
    try:
        cur = conn.cursor()
        
        # Check bucket exists
        cur.execute("""
            SELECT id, name, public, allowed_mime_types 
            FROM storage.buckets 
            WHERE id = 'experiments';
        """)
        
        bucket = cur.fetchone()
        assert bucket is not None, "Experiments bucket not found"
        
        bucket_id, name, is_public, mime_types = bucket
        assert bucket_id == 'experiments'
        assert name == 'experiments'
        assert is_public is False  # Should be private
        assert 'application/json' in mime_types
        assert 'application/octet-stream' in mime_types
        
        print(f"✓ Storage bucket configured: {name} (private={not is_public})")
        print(f"  Allowed MIME types: {len(mime_types)}")
        
        # Check storage policies
        cur.execute("""
            SELECT name, action 
            FROM storage.policies 
            WHERE bucket_id = 'experiments'
            ORDER BY name;
        """)
        
        policies = cur.fetchall()
        print(f"  Storage policies: {len(policies)}")
        
        actions = {p[1] for p in policies}
        required_actions = {'INSERT', 'SELECT', 'UPDATE', 'DELETE'}
        assert required_actions.issubset(actions), "Missing storage policies"
        
        
    finally:
        cur.close()
        conn.close()


def test_migrations():
    """Test that migrations are valid."""
    # Check migration files exist
    migration_dir = Path("supabase/migrations")
    assert migration_dir.exists(), "Migrations directory not found"
    
    migrations = sorted(migration_dir.glob("*.sql"))
    assert len(migrations) >= 2, "Expected at least 2 migration files"
    
    print(f"\nMigrations found:")
    for mig in migrations:
        print(f"  - {mig.name}")
    
    # Validate SQL syntax by attempting to parse
    for mig_file in migrations:
        content = mig_file.read_text()
        
        # Basic checks
        assert "CREATE TABLE" in content or "INSERT INTO" in content
        assert "--" in content  # Should have comments
        
        # Check for common issues
        assert "DROP TABLE" not in content, "Migrations should not drop tables"
        assert content.strip().endswith(";"), "SQL should end with semicolon"
    


def test_database_operations():
    """Test common database operations."""
    import psycopg2
    import json
    import uuid
    
    conn = psycopg2.connect(
        host="localhost",
        port=54322,
        database="postgres",
        user="postgres",
        password="postgres"
    )
    
    try:
        cur = conn.cursor()
        
        # Create experiment
        exp_name = f"test_ops_{int(time.time())}"
        cur.execute("""
            INSERT INTO experiments (experiment_name, base_path, metadata)
            VALUES (%s, %s, %s)
            RETURNING id;
        """, (exp_name, '/tmp/test', json.dumps({"test": True})))
        
        exp_id = cur.fetchone()[0]
        
        # Create multiple jobs with different priorities
        job_ids = []
        for i in range(5):
            job_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO jobs (id, experiment_id, config, priority)
                VALUES (%s, %s, %s, %s);
            """, (job_id, exp_id, json.dumps({"_target_": "test", "index": i}), i * 200))
            job_ids.append(job_id)
        
        # Test claiming a job (highest priority first)
        cur.execute("""
            UPDATE jobs 
            SET status = 'running', 
                worker_id = 'test_worker',
                started_at = NOW()
            WHERE id = (
                SELECT id FROM jobs 
                WHERE experiment_id = %s AND status = 'queued'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
            )
            RETURNING id, priority;
        """, (exp_id,))
        
        claimed = cur.fetchone()
        assert claimed is not None
        claimed_id, claimed_priority = claimed
        assert claimed_priority == 800  # Highest priority
        
        # Test heartbeat update
        cur.execute("""
            UPDATE jobs 
            SET last_heartbeat = NOW()
            WHERE id = %s AND status = 'running'
            RETURNING last_heartbeat;
        """, (claimed_id,))
        
        heartbeat = cur.fetchone()
        assert heartbeat is not None
        
        # Test job completion
        cur.execute("""
            UPDATE jobs 
            SET status = 'completed',
                completed_at = NOW(),
                final_metrics = %s
            WHERE id = %s
            RETURNING status;
        """, (json.dumps({"accuracy": 0.95}), claimed_id))
        
        status = cur.fetchone()[0]
        assert status == 'completed'
        
        # Test sync status
        cur.execute("""
            INSERT INTO sync_status (job_id, file_path, file_type, size_bytes)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """, (claimed_id, '/tmp/model.pt', 'model', 1024000))
        
        sync_id = cur.fetchone()[0]
        assert sync_id is not None
        
        conn.commit()
        
    finally:
        cur.close()
        conn.close()


```

## Validation
```bash
# Initialize Supabase project (if not done)
supabase init

# Start local Supabase
supabase start

# Run migrations
supabase db reset

# Run the test with pytest
pt tests/implementation/test_step_3_1.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_3_1.py::test_local_supabase PASSED
# tests/implementation/test_step_3_1.py::test_database_schema PASSED
# tests/implementation/test_step_3_1.py::test_storage_bucket PASSED
# tests/implementation/test_step_3_1.py::test_migrations PASSED
# tests/implementation/test_step_3_1.py::test_database_operations PASSED
# ============================== 5 passed in X.XXs ===============================

# Access Supabase Studio
open http://localhost:54323

# Check tables and data in the web UI
```

## Common Mistakes
- DO NOT: Use CASCADE deletes everywhere - be intentional about data retention
- DO NOT: Forget indexes on foreign keys and common query patterns  
- DO NOT: Use TEXT for status fields without CHECK constraints
- DO NOT: Skip row-level security - always enable it
- DO NOT: Make storage buckets public by default

## Next Step
Proceed to Step 3.2: Supabase Client Basics