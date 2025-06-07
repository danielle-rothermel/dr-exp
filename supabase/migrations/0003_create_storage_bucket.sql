-- Migration to create storage bucket for experiment artifacts
-- Date: 2025-06-06

BEGIN;

-- Create the experiment-artifacts storage bucket
-- Note: storage.buckets table is managed by Supabase
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'experiment-artifacts', 
    'experiment-artifacts', 
    false, 
    104857600, -- 100MB limit
    ARRAY['application/json', 'text/plain', 'application/zip', 'application/gzip', 'application/octet-stream']
) ON CONFLICT (id) DO NOTHING;

-- Create a policy to allow service role access to the bucket
-- This allows the SupabaseJobDB to upload/download files
INSERT INTO storage.objects (bucket_id, name, owner, metadata) 
VALUES ('experiment-artifacts', '.keep', NULL, '{}') 
ON CONFLICT DO NOTHING;

COMMIT;