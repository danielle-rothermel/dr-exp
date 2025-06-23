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