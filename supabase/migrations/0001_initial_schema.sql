-- Supabase Initial Schema for Experiment Manager
-- Version: 0001
-- Date: 2025-05-31

BEGIN;

-- Enable pgcrypto extension if not already enabled, for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA public;

-- 1. sweep_config_clusters
-- High-level groupings of logically related sweeps.
CREATE TABLE public.sweep_config_clusters (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

COMMENT ON TABLE public.sweep_config_clusters IS 'High-level groupings of logically related sweeps. Human-friendly description + shared metadata.';
COMMENT ON COLUMN public.sweep_config_clusters.id IS 'Primary key';
COMMENT ON COLUMN public.sweep_config_clusters.name IS 'Display name for the cluster';
COMMENT ON COLUMN public.sweep_config_clusters.description IS 'Optional text description; may be left blank';
COMMENT ON COLUMN public.sweep_config_clusters.created_at IS 'Timestamp of when the cluster was created';

-- 2. sweep_configs
-- Individual Hydra-resolved config instances to be used for job creation.
CREATE TABLE public.sweep_configs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    cluster_id UUID REFERENCES public.sweep_config_clusters(id) ON DELETE SET NULL, -- Or ON DELETE CASCADE if configs should be deleted with cluster
    config_json JSONB NOT NULL,
    config_hash TEXT NOT NULL,
    interface_version TEXT,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

COMMENT ON TABLE public.sweep_configs IS 'Individual Hydra-resolved config instances to be used for job creation.';
COMMENT ON COLUMN public.sweep_configs.id IS 'Primary key';
COMMENT ON COLUMN public.sweep_configs.cluster_id IS 'Foreign key to sweep_config_clusters.id';
COMMENT ON COLUMN public.sweep_configs.config_json IS 'Full resolved Hydra configuration';
COMMENT ON COLUMN public.sweep_configs.config_hash IS 'Hash of the config_json for deduplication';
COMMENT ON COLUMN public.sweep_configs.interface_version IS 'Version of the training interface used/expected';
COMMENT ON COLUMN public.sweep_configs.created_at IS 'Timestamp of when the config was registered';

-- Indexes for sweep_configs
CREATE INDEX idx_sweep_configs_cluster_id ON public.sweep_configs(cluster_id);
CREATE UNIQUE INDEX idx_sweep_configs_config_hash ON public.sweep_configs(config_hash); -- Ensure hash is unique

-- 3. jobs
-- Tracks training jobs with config references, current status, progress metrics, etc.
CREATE TABLE public.jobs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    config_id UUID REFERENCES public.sweep_configs(id) ON DELETE RESTRICT NOT NULL, -- Prevent deleting config if jobs exist
    status TEXT DEFAULT 'queued'::text NOT NULL
        CHECK (status IN ('queued', 'running', 'completed', 'failed', 'deleted')),
    retry_index INT DEFAULT 0 NOT NULL,
    assigned_worker TEXT DEFAULT 'unassigned'::text,
    heartbeat TIMESTAMPTZ,
    metrics_path TEXT DEFAULT ''::text,
    artifacts_path TEXT DEFAULT ''::text,
    num_epochs INT,
    final_val_acc REAL, -- Using REAL for float as per PostgreSQL standard
    final_train_loss REAL,
    upload_complete_at TIMESTAMPTZ,
    finalize_success BOOLEAN,
    resumable_from_run_id UUID REFERENCES public.jobs(id) ON DELETE SET NULL, -- Allows resuming from a previous job
    checkpoint_url TEXT DEFAULT ''::text,
    interface_version TEXT,
    code_version TEXT, -- Git SHA
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ
);

COMMENT ON TABLE public.jobs IS 'Tracks training jobs with config references, current status, progress metrics, logs, and output artifact pointers.';
COMMENT ON COLUMN public.jobs.id IS 'Primary key';
COMMENT ON COLUMN public.jobs.config_id IS 'Foreign key to sweep_configs.id';
COMMENT ON COLUMN public.jobs.status IS 'Job status: queued, running, completed, failed, deleted';
COMMENT ON COLUMN public.jobs.retry_index IS 'Retry count for this logical job';
COMMENT ON COLUMN public.jobs.assigned_worker IS 'Identifier of the worker process; default = "unassigned"';
COMMENT ON COLUMN public.jobs.heartbeat IS 'Last heartbeat timestamp from the worker';
COMMENT ON COLUMN public.jobs.metrics_path IS 'Path to .jsonl metrics file in Supabase Storage; default = ""';
COMMENT ON COLUMN public.jobs.artifacts_path IS 'Path to artifacts folder or archive in Supabase Storage; default = ""';
COMMENT ON COLUMN public.jobs.num_epochs IS 'Number of epochs reported by train()';
COMMENT ON COLUMN public.jobs.final_val_acc IS 'Final reported validation accuracy';
COMMENT ON COLUMN public.jobs.final_train_loss IS 'Final reported training loss';
COMMENT ON COLUMN public.jobs.upload_complete_at IS 'Timestamp when logger finalized artifact/log upload';
COMMENT ON COLUMN public.jobs.finalize_success IS 'Boolean flag indicating if the logger reported successful finalization';
COMMENT ON COLUMN public.jobs.resumable_from_run_id IS 'If this job is a resumption, points to the original job ID';
COMMENT ON COLUMN public.jobs.checkpoint_url IS 'Path to the resume checkpoint in blob storage; default = ""';
COMMENT ON COLUMN public.jobs.interface_version IS 'Interface compatibility version tag of the training code';
COMMENT ON COLUMN public.jobs.code_version IS 'Git SHA of the training code used for this job';
COMMENT ON COLUMN public.jobs.start_time IS 'Timestamp when training began';
COMMENT ON COLUMN public.jobs.end_time IS 'Timestamp when training ended (only set for completed or failed jobs)';

-- Indexes for jobs
CREATE INDEX idx_jobs_config_id ON public.jobs(config_id);
CREATE INDEX idx_jobs_status ON public.jobs(status);
CREATE INDEX idx_jobs_assigned_worker ON public.jobs(assigned_worker);
CREATE INDEX idx_jobs_heartbeat ON public.jobs(heartbeat);
CREATE INDEX idx_jobs_interface_version ON public.jobs(interface_version);
CREATE INDEX idx_jobs_code_version ON public.jobs(code_version);
CREATE INDEX idx_jobs_resumable_from_run_id ON public.jobs(resumable_from_run_id);


-- 4. metrics
-- Optional per-epoch or per-step summary table.
CREATE TABLE public.metrics (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, -- Using BIGINT for auto-incrementing ID
    job_id UUID REFERENCES public.jobs(id) ON DELETE CASCADE NOT NULL,
    epoch INT,
    step INT,
    metric TEXT NOT NULL,
    value REAL NOT NULL, -- Using REAL for float
    logged_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

COMMENT ON TABLE public.metrics IS 'Optional per-epoch or per-step summary table. Can be used for UI previews, live streaming, or downsampled plotting.';
COMMENT ON COLUMN public.metrics.id IS 'Primary key for the metric entry';
COMMENT ON COLUMN public.metrics.job_id IS 'Foreign key to jobs.id, linking metric to a specific job';
COMMENT ON COLUMN public.metrics.epoch IS 'Epoch number for the metric';
COMMENT ON COLUMN public.metrics.step IS 'Optional step number within an epoch, for step-based logging';
COMMENT ON COLUMN public.metrics.metric IS 'Name of the metric (e.g., train_loss, val_accuracy)';
COMMENT ON COLUMN public.metrics.value IS 'Scalar value of the metric';
COMMENT ON COLUMN public.metrics.logged_at IS 'Timestamp when the metric was logged';

-- Indexes for metrics
CREATE INDEX idx_metrics_job_id ON public.metrics(job_id);
CREATE INDEX idx_metrics_job_metric_epoch_step ON public.metrics(job_id, metric, epoch, step); -- Composite for typical queries


-- 5. errors
-- Captures structured tracebacks and failure causes for post-mortem inspection.
CREATE TABLE public.errors (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    job_id UUID REFERENCES public.jobs(id) ON DELETE CASCADE NOT NULL,
    error_type TEXT NOT NULL,
    message TEXT,
    stacktrace TEXT,
    timestamp TIMESTAMPTZ DEFAULT now() NOT NULL
);

COMMENT ON TABLE public.errors IS 'Captures structured tracebacks and failure causes for post-mortem inspection.';
COMMENT ON COLUMN public.errors.id IS 'Primary key for the error entry';
COMMENT ON COLUMN public.errors.job_id IS 'Foreign key to jobs.id, linking error to a specific job';
COMMENT ON COLUMN public.errors.error_type IS 'Type of error (e.g., nan_failure, crash, timeout)';
COMMENT ON COLUMN public.errors.message IS 'Short summary of the error or exception class';
COMMENT ON COLUMN public.errors.stacktrace IS 'Nullable full stacktrace, if available';
COMMENT ON COLUMN public.errors.timestamp IS 'Timestamp of when the failure occurred';

-- Indexes for errors
CREATE INDEX idx_errors_job_id ON public.errors(job_id);
CREATE INDEX idx_errors_error_type ON public.errors(error_type);


-- 6. failures
-- Keeps a retry log for auditability and diagnosis of repeated failures.
CREATE TABLE public.failures (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    job_id UUID REFERENCES public.jobs(id) ON DELETE CASCADE NOT NULL,
    retry_index INT NOT NULL,
    error_type TEXT, -- Matched to errors.error_type or other failure reason
    timestamp TIMESTAMPTZ DEFAULT now() NOT NULL
);

COMMENT ON TABLE public.failures IS 'Keeps a retry log for auditability and diagnosis of repeated failures.';
COMMENT ON COLUMN public.failures.id IS 'Primary key for the failure log entry';
COMMENT ON COLUMN public.failures.job_id IS 'Foreign key to jobs.id, indicating which job this failure instance relates to';
COMMENT ON COLUMN public.failures.retry_index IS 'The retry attempt number for the job when this failure occurred';
COMMENT ON COLUMN public.failures.error_type IS 'Type of error associated with this failure, can match errors.error_type';
COMMENT ON COLUMN public.failures.timestamp IS 'Timestamp of when this specific failure instance occurred';

-- Indexes for failures
CREATE INDEX idx_failures_job_id ON public.failures(job_id);
CREATE INDEX idx_failures_job_id_retry_index ON public.failures(job_id, retry_index);


-- Grant usage on schema public to supabase_admin and postgres to allow table creation/modification
-- This is typically handled by Supabase default roles, but explicit grant can be useful.
GRANT USAGE ON SCHEMA public TO supabase_admin;
GRANT USAGE ON SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO supabase_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;

-- Note: Row Level Security (RLS) is not enabled by default on these tables.
-- You should enable RLS and define policies if you need fine-grained access control.
-- Example:
-- ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Allow public read access" ON public.jobs FOR SELECT USING (true);
-- CREATE POLICY "Allow individual user to update their own jobs" ON public.jobs FOR UPDATE USING (auth.uid() = user_id_column) WITH CHECK (auth.uid() = user_id_column);

COMMIT;

