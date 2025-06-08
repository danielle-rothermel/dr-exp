#!/usr/bin/env python3
"""Convenience script for running Supabase integration tests.

This script handles starting Supabase if needed and running the tests
with proper environment configuration.
"""

import os
import sys
import subprocess
import time


def check_supabase_running():
    """Check if local Supabase is running."""
    try:
        result = subprocess.run(
            ["supabase", "status"], capture_output=True, text=True, timeout=10
        )
        return (
            result.returncode == 0
            and "API URL: http://127.0.0.1:54321" in result.stdout
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return False


def start_supabase():
    """Start local Supabase if not running."""
    if check_supabase_running():
        print("✅ Supabase is already running")
        return True

    print("🚀 Starting Supabase...")
    try:
        # Start Supabase in the background
        subprocess.Popen(
            ["supabase", "start"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for it to start (timeout after 2 minutes)
        for _ in range(24):  # 24 * 5 = 120 seconds
            if check_supabase_running():
                print("✅ Supabase started successfully")
                return True
            time.sleep(5)
            print("⏳ Waiting for Supabase to start...")

        print("❌ Supabase failed to start within timeout")
        return False

    except Exception as e:
        print(f"❌ Failed to start Supabase: {e}")
        return False


def run_tests(test_type="isolated", reset_db=False):
    """Run Supabase integration tests."""
    # Set environment variables
    env = os.environ.copy()
    env["EXPMGR_MODE"] = "supabase_local"
    env["RUN_SUPABASE_TESTS"] = "1"

    # Reset database if requested
    if reset_db:
        print("🗂️  Resetting Supabase database...")
        try:
            subprocess.run(["supabase", "db", "reset"], check=True, env=env)
            print("✅ Database reset complete")
        except subprocess.CalledProcessError as e:
            print(f"❌ Database reset failed: {e}")
            return False

    # Choose test files based on type
    if test_type == "isolated":
        test_path = "tests/job_db/test_supabase_isolated.py"
    elif test_type == "integration":
        test_path = "tests/job_db/test_supabase_integration.py"
    elif test_type == "all":
        test_path = "tests/job_db/test_supabase_*.py"
    else:
        test_path = test_type  # Allow custom paths

    # Run pytest
    print(f"🧪 Running tests: {test_path}")
    cmd = ["uv", "run", "pytest", test_path, "-v", "--tb=short"]

    try:
        result = subprocess.run(cmd, env=env)
        return result.returncode == 0
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run Supabase integration tests")
    parser.add_argument(
        "--type",
        choices=["isolated", "integration", "all"],
        default="isolated",
        help="Type of tests to run (default: isolated)",
    )
    parser.add_argument(
        "--reset-db", action="store_true", help="Reset database before running tests"
    )
    parser.add_argument(
        "--no-start", action="store_true", help="Don't automatically start Supabase"
    )
    parser.add_argument("test_path", nargs="?", help="Custom test path to run")

    args = parser.parse_args()

    # Check/start Supabase
    if not args.no_start:
        if not start_supabase():
            print("❌ Could not start Supabase. Tests cannot run.")
            sys.exit(1)
    elif not check_supabase_running():
        print(
            "❌ Supabase is not running. Start it with 'supabase start' or remove --no-start"
        )
        sys.exit(1)

    # Run tests
    test_type = args.test_path or args.type
    success = run_tests(test_type, reset_db=args.reset_db)

    if success:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
