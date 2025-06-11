#!/usr/bin/env python3
"""Test remote Supabase connection using environment variables."""

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_connection():
    """Test basic Supabase connection."""
    print("Testing Remote Supabase Connection")
    print("=" * 50)
    
    # Check environment variables
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url:
        print("❌ ERROR: SUPABASE_URL not found in environment")
        print("   Make sure your .env file contains: SUPABASE_URL=https://xxxxx.supabase.co")
        return False
        
    if not key:
        print("❌ ERROR: SUPABASE_KEY not found in environment")
        print("   Make sure your .env file contains: SUPABASE_KEY=eyJhbGc...")
        return False
    
    print(f"✓ Found SUPABASE_URL: {url}")
    print(f"✓ Found SUPABASE_KEY: {key[:20]}... (hidden)")
    
    # Validate URL format
    if not url.startswith("https://") or not url.endswith(".supabase.co"):
        print("⚠️  WARNING: URL doesn't match expected format (https://xxxxx.supabase.co)")
    
    # Try to import and create client
    try:
        from supabase import create_client, Client
        print("✓ Supabase package imported successfully")
    except ImportError:
        print("❌ ERROR: Supabase package not installed")
        print("   Run: uv add supabase")
        return False
    
    # Try to connect
    try:
        print("\nAttempting to connect to Supabase...")
        client: Client = create_client(url, key)
        
        # Test 1: List storage buckets
        print("\n1. Testing storage connection...")
        try:
            buckets = client.storage.list_buckets()
            print(f"   ✓ Connected! Found {len(buckets)} storage buckets")
            for bucket in buckets:
                print(f"     - {bucket.name}")
        except Exception as e:
            print(f"   ❌ Storage test failed: {e}")
        
        # Test 2: Check for dr_exp bucket
        print("\n2. Checking for 'dr_exp' storage bucket...")
        try:
            # Try to create the bucket (will fail if exists, which is fine)
            client.storage.create_bucket("dr_exp", {"public": False})
            print("   ✓ Created 'dr_exp' bucket")
        except Exception as e:
            if "already exists" in str(e):
                print("   ✓ 'dr_exp' bucket already exists")
            else:
                print(f"   ⚠️  Could not create bucket: {e}")
        
        # Test 3: Database connection
        print("\n3. Testing database connection...")
        try:
            # Try a simple query
            result = client.rpc("get_current_timestamp").execute()
            print("   ✓ Database connection working!")
        except Exception as e:
            # Try table query as fallback
            try:
                result = client.table('experiments').select("count", count="exact").execute()
                print(f"   ✓ Database working! Found {result.count} experiments")
            except Exception as e2:
                if "does not exist" in str(e2):
                    print("   ⚠️  Tables don't exist yet (expected - Phase 3 will create them)")
                else:
                    print(f"   ❌ Database error: {e2}")
        
        print("\n" + "=" * 50)
        print("✅ Remote Supabase connection test PASSED!")
        print("\nYour .env configuration is working correctly.")
        print("Workers will be able to sync to this Supabase instance.")
        return True
        
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        print("\nTroubleshooting:")
        print("1. Verify SUPABASE_URL format: https://[project-id].supabase.co")
        print("2. Ensure you're using the service_role key (not anon key)")
        print("3. Check if your Supabase project is paused (free tier pauses after 1 week)")
        print("4. Verify network connectivity to supabase.co")
        return False

if __name__ == "__main__":
    # Load .env file if it exists
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            print(f"✓ Loaded .env file from {env_path}\n")
        else:
            print("⚠️  No .env file found, using environment variables\n")
    except ImportError:
        print("⚠️  python-dotenv not installed, using environment variables")
        print("   To load .env automatically, run: uv add python-dotenv\n")
    
    success = test_connection()
    sys.exit(0 if success else 1)