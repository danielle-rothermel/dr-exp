#!/usr/bin/env python3
"""Check remote Supabase database state."""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_KEY must be set in .env")
    sys.exit(1)

print("🔍 Checking remote Supabase database...")
print(f"   URL: {SUPABASE_URL}")

# Create client
client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Try to query existing tables
try:
    # Check if experiments table exists
    response = client.table("experiments").select("*").limit(1).execute()
    print("\n✅ 'experiments' table exists")
    print(f"   Records: {len(response.data) if response.data else 0}")

    # Check jobs table
    response = client.table("jobs").select("*").limit(1).execute()
    print("✅ 'jobs' table exists")

    # Check sync_status table
    response = client.table("sync_status").select("*").limit(1).execute()
    print("✅ 'sync_status' table exists")

    print("\n⚠️  WARNING: Tables already exist in remote database!")
    print("   Running migrations will DROP and recreate these tables.")

except Exception as e:
    if "relation" in str(e) and "does not exist" in str(e):
        print("\n✅ No existing tables found - safe to deploy")
    else:
        print(f"\n❌ Error checking tables: {e}")

# Check storage buckets
try:
    buckets = client.storage.list_buckets()
    bucket_names = [b.name for b in buckets]

    print(f"\n📦 Storage buckets: {bucket_names}")
    if "experiments" in bucket_names:
        print("   ⚠️  'experiments' bucket already exists")

        # Check if there are files
        try:
            files = client.storage.from_("experiments").list()
            print(f"   Files in bucket: {len(files) if files else 0}")
        except:
            pass

except Exception as e:
    print(f"\n❌ Error checking storage: {e}")

print("\n" + "=" * 50)
print("Ready to deploy? The deployment will:")
print("1. DROP all existing tables (experiments, jobs, sync_status)")
print("2. Recreate tables with latest schema")
print("3. Create/update storage bucket and policies")
print("\nThis will DELETE all existing data!")
print("=" * 50)
