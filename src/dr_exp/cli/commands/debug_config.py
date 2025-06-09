"""Debug config command to show system configuration."""

import os
from argparse import ArgumentParser, Namespace

from dr_exp.cli.base_command import BaseCommand
from dr_exp.job_db.config import JobDBConfig


class DebugConfigCommand(BaseCommand):
    """Show detailed system configuration information."""

    @property
    def name(self) -> str:
        return "debug-config"

    @property
    def help(self) -> str:
        return "Show detailed system configuration"

    @property
    def description(self) -> str:
        return "Display current configuration values, environment variables, and paths"

    def add_arguments(self, parser: ArgumentParser) -> None:
        pass  # No arguments needed

    def run(self, args: Namespace) -> int:
        """Show detailed configuration information."""
        try:
            # Get configuration
            config = JobDBConfig.from_env()
            system = self.create_system()
            
            print("🔧 System Configuration")
            print("=" * 50)
            
            # Environment variables
            print("\n📋 Environment Variables:")
            env_vars = [
                ("EXPMGR_MODE", config.mode),
                ("DR_EXP_BASE_PATH", config.base_path),
                ("DR_EXP_STORAGE_PATH", config.storage_path),
                ("SUPABASE_URL", config.supabase_url or "Not set"),
                ("SUPABASE_KEY", "***" if config.supabase_key else "Not set"),
                ("DEBUG", os.getenv("DEBUG", "Not set")),
            ]
            
            for name, value in env_vars:
                print(f"  {name}: {value}")
            
            # Computed paths
            print(f"\n📁 Computed Paths:")
            jobs_dir = os.path.join(config.base_path, "job_data")
            print(f"  Jobs directory: {jobs_dir}")
            print(f"  Jobs directory exists: {os.path.exists(jobs_dir)}")
            print(f"  Storage directory: {config.storage_path}")
            print(f"  Storage directory exists: {os.path.exists(config.storage_path)}")
            
            # Database information
            print(f"\n🗄️  Database Configuration:")
            print(f"  Mode: {config.mode}")
            print(f"  Is Supabase mode: {config.is_supabase_mode()}")
            
            if config.mode == "files_local":
                try:
                    job_files = [f for f in os.listdir(jobs_dir) if f.endswith('.json')] if os.path.exists(jobs_dir) else []
                    print(f"  Job files in directory: {len(job_files)}")
                except OSError as e:
                    print(f"  Error reading job files: {e}")
            
            # System factory information
            print(f"\n⚙️  System Factory:")
            factory_config = system.config
            print(f"  GPUs: {factory_config.gpus}")
            print(f"  Workers per GPU: {factory_config.workers_per_gpu}")
            print(f"  Total worker capacity: {len(factory_config.gpus) * factory_config.workers_per_gpu}")
            print(f"  Heartbeat timeout: {factory_config.heartbeat_timeout}s")
            print(f"  Manager base dir: {factory_config.manager_base_dir}")
            
            # Environment detection
            env_info = factory_config.get_environment_info()
            print(f"\n🌐 Environment Detection:")
            print(f"  Scheduler: {env_info['scheduler']}")
            print(f"  Node name: {env_info['node_name']}")
            print(f"  Process ID: {env_info['process_id']}")
            if env_info['scheduler'] == 'slurm':
                print(f"  SLURM Job ID: {env_info.get('job_id', 'N/A')}")
                print(f"  SLURM Node list: {env_info.get('node_list', 'N/A')}")
            
            # Validation
            print(f"\n✅ Validation:")
            try:
                config.validate()
                factory_config.validate()
                print("  Configuration is valid")
            except Exception as e:
                print(f"  ❌ Configuration error: {e}")
                return 1
            
            return 0
            
        except Exception as e:
            print(f"❌ Error retrieving configuration: {e}")
            return 1