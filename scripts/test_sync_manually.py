#!/usr/bin/env python3
"""Manually test sync with proper string conversion."""

import os
from pathlib import Path
from dr_exp.sync.supabase_client import SupabaseClient
from dr_exp.sync.queue import SyncQueue

# Initialize client
client = SupabaseClient()
print("✓ Supabase client initialized")

# Get or create experiment with string path
exp_name = "sync_test_fresh"
base_path = "/scratch/ddr8143/repos/dr_exp/test_runs"  # String, not Path
exp_id = client.get_or_create_experiment(exp_name, base_path)
print(f"✓ Experiment ID: {exp_id}")

# Process sync queue
queue_path = Path(base_path) / exp_name / "sync_queue"
sync_queue = SyncQueue(queue_path)
pending = sync_queue.get_pending_items(limit=2)
print(f"\n✓ Found {len(pending)} pending items")

# Upload files
for item in pending:
    print(f"\nProcessing: {item.id}")
    try:
        # Upload file
        with open(item.file_path, 'rb') as f:
            file_data = f.read()
        
        storage_path = f"{exp_id}/{item.job_id}/{Path(item.file_path).name}"
        
        # Upload to storage
        result = client.client.storage.from_('experiments').upload(
            storage_path,
            file_data,
            {'content-type': 'application/json'}
        )
        print(f"  ✓ Uploaded to: {storage_path}")
        
        # Create sync status record
        client.create_sync_status(
            job_id=item.job_id,
            file_path=str(item.file_path),  # Convert to string
            file_type=item.file_type,
            checksum=item.checksum,
            size_bytes=item.size_bytes,
            storage_url=f"experiments/{storage_path}",
            metadata=item.metadata
        )
        print(f"  ✓ Created sync status record")
        
        # Mark as completed
        sync_queue.mark_attempt(item.id)
        print(f"  ✓ Marked as completed in queue")
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        sync_queue.mark_attempt(item.id, str(e))

print("\n✅ Sync test complete!")