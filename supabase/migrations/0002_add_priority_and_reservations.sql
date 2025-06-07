-- Migration to add priority system and job reservations
-- Date: 2025-06-06

BEGIN;

-- Add priority column to jobs table
ALTER TABLE public.jobs 
ADD COLUMN priority INT DEFAULT 100 NOT NULL
    CHECK (priority >= 0 AND priority <= 1000);

-- Add job reservation columns
ALTER TABLE public.jobs 
ADD COLUMN reserved_for_worker TEXT,
ADD COLUMN reservation_expires_at TIMESTAMPTZ;

-- Add created_at timestamp to jobs table (missing from initial schema)
ALTER TABLE public.jobs 
ADD COLUMN created_at TIMESTAMPTZ DEFAULT now() NOT NULL;

-- Add indexes for priority and reservations
CREATE INDEX idx_jobs_priority ON public.jobs(priority);
CREATE INDEX idx_jobs_priority_status ON public.jobs(priority, status);
CREATE INDEX idx_jobs_reserved_for_worker ON public.jobs(reserved_for_worker);
CREATE INDEX idx_jobs_reservation_expires_at ON public.jobs(reservation_expires_at);
CREATE INDEX idx_jobs_created_at ON public.jobs(created_at);

-- Update status check constraint to include 'killed' status
ALTER TABLE public.jobs 
DROP CONSTRAINT jobs_status_check;

ALTER TABLE public.jobs 
ADD CONSTRAINT jobs_status_check 
CHECK (status IN ('queued', 'running', 'completed', 'failed', 'killed', 'deleted'));

-- Add comments for new columns
COMMENT ON COLUMN public.jobs.priority IS 'Job priority for queue ordering (0-1000). Higher values indicate higher priority.';
COMMENT ON COLUMN public.jobs.reserved_for_worker IS 'Worker ID that can claim this reserved job. NULL for unreserved jobs.';
COMMENT ON COLUMN public.jobs.reservation_expires_at IS 'Expiration time for job reservation. NULL for permanent reservations.';
COMMENT ON COLUMN public.jobs.created_at IS 'Timestamp when the job was created';

-- Create storage bucket for experiment artifacts if it doesn't exist
-- Note: This is handled by Supabase, but we document the expected bucket name
-- INSERT INTO storage.buckets (id, name, public) VALUES ('experiment-artifacts', 'experiment-artifacts', false) ON CONFLICT DO NOTHING;

-- Create PostgreSQL function for atomic job claiming with priority support
CREATE OR REPLACE FUNCTION claim_next_job(worker_id_input TEXT)
RETURNS TABLE(
    id UUID,
    config_id UUID,
    status TEXT,
    retry_index INT,
    assigned_worker TEXT,
    heartbeat TIMESTAMPTZ,
    metrics_path TEXT,
    artifacts_path TEXT,
    num_epochs INT,
    final_val_acc REAL,
    final_train_loss REAL,
    upload_complete_at TIMESTAMPTZ,
    finalize_success BOOLEAN,
    resumable_from_run_id UUID,
    checkpoint_url TEXT,
    interface_version TEXT,
    code_version TEXT,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    priority INT,
    reserved_for_worker TEXT,
    reservation_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ
) 
LANGUAGE plpgsql
AS $$
DECLARE
    claimed_job_id UUID;
BEGIN
    -- Find and claim the next available job atomically
    -- Priority: reserved jobs for this worker > unreserved jobs by priority > expired reservations
    UPDATE public.jobs 
    SET 
        status = 'running',
        assigned_worker = worker_id_input,
        heartbeat = now(),
        start_time = COALESCE(jobs.start_time, now())
    WHERE jobs.id = (
        SELECT j.id 
        FROM public.jobs j
        WHERE j.status = 'queued'
          AND (
            -- Case 1: Job is reserved for this specific worker and not expired
            (j.reserved_for_worker = worker_id_input 
             AND (j.reservation_expires_at IS NULL OR j.reservation_expires_at > now()))
            OR 
            -- Case 2: Job is not reserved (unreserved jobs)
            (j.reserved_for_worker IS NULL)
            OR
            -- Case 3: Job reservation has expired
            (j.reserved_for_worker IS NOT NULL 
             AND j.reservation_expires_at IS NOT NULL 
             AND j.reservation_expires_at <= now())
          )
        ORDER BY 
            -- Prioritize reserved jobs for this worker
            CASE WHEN j.reserved_for_worker = worker_id_input THEN 1 ELSE 2 END,
            -- Then by priority (higher first)
            j.priority DESC,
            -- Then by creation time (older first)
            j.created_at ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING jobs.id INTO claimed_job_id;
    
    -- Return the claimed job details if one was found
    IF claimed_job_id IS NOT NULL THEN
        RETURN QUERY
        SELECT j.id, j.config_id, j.status, j.retry_index, j.assigned_worker, 
               j.heartbeat, j.metrics_path, j.artifacts_path, j.num_epochs, 
               j.final_val_acc, j.final_train_loss, j.upload_complete_at, 
               j.finalize_success, j.resumable_from_run_id, j.checkpoint_url, 
               j.interface_version, j.code_version, j.start_time, j.end_time,
               j.priority, j.reserved_for_worker, j.reservation_expires_at, j.created_at
        FROM public.jobs j
        WHERE j.id = claimed_job_id;
    END IF;
END;
$$;

-- Add comment for the function
COMMENT ON FUNCTION claim_next_job(TEXT) IS 'Atomically claims the next available job for a worker, respecting priority and reservations';

COMMIT;