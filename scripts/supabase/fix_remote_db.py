#!/usr/bin/env python3
"""Fix remote database schema by running SQL directly."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Load environment
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_KEY must be set in .env")
    sys.exit(1)

print("🔧 Fixing remote database schema...")
print(f"   URL: {SUPABASE_URL}")

# Read the SQL file
sql_file = Path(__file__).parent / "fix_remote_schema.sql"
if not sql_file.exists():
    print(f"❌ SQL file not found: {sql_file}")
    sys.exit(1)

with open(sql_file, "r") as f:
    sql_content = f.read()

# Since Supabase Python client doesn't support running raw SQL directly,
# we'll need to use the REST API

# Extract project ref from URL
project_ref = SUPABASE_URL.split("//")[1].split(".")[0]

print(f"\n📝 Project ref: {project_ref}")
print("⚠️  This will DROP and recreate all tables!")
print("\nTo proceed, run this SQL in the Supabase Dashboard:")
print(f"1. Go to: https://supabase.com/dashboard/project/{project_ref}/sql/new")
print("2. Paste the contents of scripts/fix_remote_schema.sql")
print("3. Click 'Run' to execute")
print("\nAlternatively, you can use the Supabase CLI:")
print("cat scripts/fix_remote_schema.sql | supabase db remote set")

# Test current state
client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("\n📊 Current database state:")
for table in ["experiments", "jobs", "sync_status"]:
    try:
        result = client.table(table).select("count", count="exact").execute()
        print(f"  ✅ {table}: {result.count} rows")
    except Exception as e:
        if "does not exist" in str(e):
            print(f"  ❌ {table}: not found")
        else:
            print(f"  ❌ {table}: {e}")
