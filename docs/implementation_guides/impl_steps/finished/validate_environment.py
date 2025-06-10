#!/usr/bin/env python3
"""Validate that the development environment is ready for implementation."""
import subprocess
import sys
import os
from pathlib import Path


def check_command(cmd, name, min_version=None):
    """Check if a command exists and optionally its version."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            output = result.stdout.strip()
            print(f"✓ {name}: {output}")
            return True
        else:
            print(f"✗ {name}: Command failed")
            return False
    except FileNotFoundError:
        print(f"✗ {name}: Not found")
        return False


def check_python_package(package):
    """Check if a Python package is installed."""
    try:
        result = subprocess.run(
            ["uv", "pip", "show", package], 
            capture_output=True, 
            text=True
        )
        if result.returncode == 0:
            # Extract version
            for line in result.stdout.split('\n'):
                if line.startswith('Version:'):
                    version = line.split(':', 1)[1].strip()
                    print(f"✓ {package}: {version}")
                    return True
        print(f"✗ {package}: Not installed")
        return False
    except:
        print(f"✗ {package}: Could not check")
        return False


def check_git_branch():
    """Check that we're not on main/master branch."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"], 
            capture_output=True, 
            text=True
        )
        branch = result.stdout.strip()
        if branch in ["main", "master"]:
            print(f"⚠ Git branch: On {branch} - should be on feature branch!")
            return False
        else:
            print(f"✓ Git branch: {branch}")
            return True
    except:
        print("✗ Git branch: Could not check")
        return False


def check_aliases():
    """Check if required aliases exist."""
    # This is tricky since aliases are shell-specific
    # We'll just check if the commands would work
    checks = []
    
    # Check ckdr (should run ruff and mypy)
    ckdr_works = os.system("ckdr --help >/dev/null 2>&1") == 0
    if ckdr_works:
        print("✓ ckdr alias: Available")
        checks.append(True)
    else:
        print("⚠ ckdr alias: Not found (should run: uv run ruff check . && uv run ruff format . && uv run mypy .)")
        checks.append(False)
    
    # Check pt (should run pytest)
    pt_works = os.system("pt --version >/dev/null 2>&1") == 0
    if pt_works:
        print("✓ pt alias: Available")
        checks.append(True)
    else:
        print("⚠ pt alias: Not found (should run: uv run pytest)")
        checks.append(False)
    
    return all(checks)


def main():
    """Run all environment checks."""
    print("=== Dr_Exp Implementation Environment Check ===\n")
    
    all_good = True
    
    print("Basic Tools:")
    all_good &= check_command(["python", "--version"], "Python", "3.10")
    all_good &= check_command(["uv", "--version"], "uv")
    all_good &= check_command(["git", "--version"], "Git")
    
    print("\nPython Packages:")
    all_good &= check_python_package("pytest")
    all_good &= check_python_package("mypy")
    all_good &= check_python_package("ruff")
    
    print("\nOptional but Recommended:")
    check_python_package("pytest-cov")
    check_python_package("pytest-xdist")
    
    print("\nGit Status:")
    all_good &= check_git_branch()
    
    print("\nShell Aliases:")
    check_aliases()  # Don't fail on aliases since they're convenience
    
    print("\nProject Structure:")
    if Path("src/dr_exp").exists():
        print("✓ Project structure: src/dr_exp exists")
    else:
        print("✗ Project structure: src/dr_exp not found")
        all_good = False
    
    print("\n" + "="*50)
    if all_good:
        print("✅ Environment is ready for implementation!")
        print("\nNext steps:")
        print("1. Run: docs/implementation_guides/impl_steps/PYTEST_UPDATE_PROMPT.md")
        print("2. Run: Step 0 - Clean Slate Preparation")
        return 0
    else:
        print("❌ Environment needs setup!")
        print("\nFix the issues above before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())