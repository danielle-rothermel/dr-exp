"""Configuration for JobDB instances."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class JobDBConfig:
    """Configuration for JobDB instances.
    
    This configuration class provides a unified way to configure both LocalJobDB
    and SupabaseJobDB instances, supporting environment-based configuration
    and validation.
    """
    # Common settings
    base_path: str = "."
    storage_path: str = "./storage"
    
    # Supabase-specific (optional)
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None
    
    # Mode determination
    mode: str = "files_local"  # "files_local" or "supabase_remote"
    
    @classmethod
    def from_env(cls) -> "JobDBConfig":
        """Create config from environment variables.
        
        Reads configuration from standard environment variables:
        - EXPMGR_MODE: "files_local" or "supabase_remote"
        - DR_EXP_BASE_PATH: Base directory for job data
        - DR_EXP_STORAGE_PATH: Storage directory for artifacts
        - SUPABASE_URL: Supabase project URL (required for supabase_remote mode)
        - SUPABASE_KEY: Supabase API key (required for supabase_remote mode)
        
        Returns
        -------
        JobDBConfig
            Configuration instance with values from environment.
        """
        mode = os.getenv("EXPMGR_MODE", "files_local")
        supabase_key = None
        if mode == "supabase_remote":
            # Try both possible key environment variable names
            supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
        
        return cls(
            mode=mode,
            base_path=os.getenv("DR_EXP_BASE_PATH", "."),
            storage_path=os.getenv("DR_EXP_STORAGE_PATH", "./storage"),
            supabase_url=os.getenv("SUPABASE_URL") if mode == "supabase_remote" else None,
            supabase_key=supabase_key,
        )
    
    def validate(self) -> None:
        """Validate configuration settings.
        
        Raises
        ------
        ValueError
            If configuration is invalid (e.g., missing Supabase credentials
            for supabase_remote mode, invalid URL format).
        """
        if self.mode == "supabase_remote":
            if not self.supabase_url or not self.supabase_key:
                raise ValueError("Supabase URL and Key required for supabase_remote mode")
            if not self.supabase_url.startswith(("http://", "https://")):
                raise ValueError("Invalid Supabase URL format")
        
        # Ensure paths are absolute for consistency
        self.base_path = os.path.abspath(self.base_path)
        self.storage_path = os.path.abspath(self.storage_path)
    
    def is_supabase_mode(self) -> bool:
        """Check if configuration is for Supabase mode.
        
        Returns
        -------
        bool
            True if mode is "supabase_remote" and Supabase credentials are available.
        """
        return self.mode == "supabase_remote" and bool(self.supabase_url and self.supabase_key)