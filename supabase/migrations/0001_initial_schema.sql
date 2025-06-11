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