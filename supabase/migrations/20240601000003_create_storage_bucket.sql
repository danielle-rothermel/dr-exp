-- Create storage bucket for experiment artifacts
-- Note: This uses Supabase's SQL functions to create buckets

-- First, ensure the storage schema exists
CREATE SCHEMA IF NOT EXISTS storage;

-- Create the experiments bucket using storage RPC function
SELECT storage.create_bucket(
    'experiments',
    jsonb_build_object(
        'public', false,
        'avif_autodetection', false,
        'allowed_mime_types', ARRAY[
            'application/json',
            'text/plain', 
            'application/octet-stream',
            'application/x-python-pickle',
            'application/x-hdf5',
            'application/gzip',
            'application/zip'
        ]::text[]
    )
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