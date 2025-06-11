#!/usr/bin/env python3
"""Simple test to populate remote database."""

import os
import sys
from pathlib import Path

# Ensure we're in the right directory
os.chdir(Path(__file__).parent.parent)

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Import dr_exp modules
from dr_exp.core.job_db import JobDB
from dr_exp.sync.supabase_client import SupabaseClient

print("🚀 Simple Remote Database Population Test")
print("=" * 50)

# Create a test experiment
base_path = "./simple_test"
experiment = "remote_demo"

# Initialize JobDB
print("\n1. Creating local experiment...")
job_db = JobDB(base_path=base_path, experiment_name=experiment)

# Create a test job
print("\n2. Creating test job...")
config = {
    "_target_": "dr_exp.trainers.test_trainer.train",
    "epochs": 1,
    "batch_size": 32,
}
job_id = job_db.create_job(config=config, priority=100)
print(f"   Created job: {job_id}")

# Initialize Supabase client
print("\n3. Connecting to Supabase...")
try:
    client = SupabaseClient()
    print("   ✅ Connected to Supabase")
except Exception as e:
    print(f"   ❌ Failed to connect: {e}")
    sys.exit(1)

# Create experiment in remote
print("\n4. Creating experiment in remote database...")
try:
    exp_id = client.get_or_create_experiment(
        experiment_name=experiment,
        base_path=base_path
    )
    print(f"   ✅ Experiment created/found: {exp_id}")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)

# Sync the job
print("\n5. Syncing job to remote database...")
try:
    job_data = job_db.get_job(job_id)
    success = client.sync_job(job_data, exp_id)
    if success:
        print(f"   ✅ Job synced successfully")
    else:
        print(f"   ❌ Job sync failed")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Create a test sync_status entry
print("\n6. Creating sync_status entry...")
try:
    import uuid
    from datetime import datetime, UTC
    
    # Insert directly into sync_status table
    sync_data = {
        "id": str(uuid.uuid4()),
        "job_id": job_id,
        "file_path": f"{base_path}/{experiment}/storage/{job_id}/test_file.txt",
        "file_type": "test",
        "status": "completed",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "size_bytes": 1024,
        "checksum": "abc123",
        "storage_url": f"https://example.com/test/{job_id}/test_file.txt"
    }
    
    result = client.client.table("sync_status").insert(sync_data).execute()
    if result.data:
        print(f"   ✅ Sync status entry created")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check final state
print("\n7. Checking remote database state...")
try:
    # Count experiments
    exp_count = client.client.table("experiments").select("*", count="exact").execute()
    print(f"   Experiments: {exp_count.count}")
    
    # Count jobs
    job_count = client.client.table("jobs").select("*", count="exact").execute()
    print(f"   Jobs: {job_count.count}")
    
    # Count sync_status
    sync_count = client.client.table("sync_status").select("*", count="exact").execute()
    print(f"   Sync status entries: {sync_count.count}")
except Exception as e:
    print(f"   Error checking: {e}")

print("\n✅ Test complete!")
print("\nCheck your Supabase dashboard at:")
print("https://supabase.com/dashboard/project/yfawygsfsuwrqvohsayp/editor")