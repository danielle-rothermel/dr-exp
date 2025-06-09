"""Configuration for JobDB instances."""

import os
from dataclasses import dataclass
from typing import Optional

MODES = ["files_local", "supabase_local", "supabase_remote"]

@dataclass
class JobDBConfig:
    """Configuration for JobDB instances.

    This configuration class provides a unified way to configure both LocalJobDB
    and SupabaseJobDB instances using explicit parameters.
    """

    # Required settings
    base_path: str
    mode: str  # "files_local", "supabase_local", or "supabase_remote"

    # Optional settings with defaults
    storage_path: Optional[str] = None
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        self.validate()

    def validate(self) -> None:
        """Validate configuration settings.

        Raises
        ------
        AssertionError
            If configuration is invalid (e.g., missing Supabase credentials
            for supabase_remote mode, invalid URL format).
        """
        # Validate mode
        assert self.mode in MODES, f"Mode '{self.mode}' not in: {MODES}"

        # Read Supabase credentials from environment variables
        if self.is_supabase_mode():
            if not self.supabase_url:
                self.supabase_url = os.getenv("SUPABASE_URL")
            if not self.supabase_key:
                self.supabase_key = os.getenv("SUPABASE_KEY")
            self._validate_supabase()

        # Set default storage path if not provided
        if self.storage_path is None:
            self.storage_path = os.path.join(self.base_path, "storage")

        # Ensure paths are absolute for consistency
        self.base_path = os.path.abspath(self.base_path)
        self.storage_path = os.path.abspath(self.storage_path)

    def is_supabase_mode(self) -> bool:
        """Check if configuration is for Supabase mode.

        Returns
        -------
        bool
            True if mode is "supabase_remote" or "supabase_local" 
        """
        return self.mode in ["supabase_remote", "supabase_local"]

    def _validate_supabase(self) -> None:
        assert self.supabase_url is not None, "Set SUPABASE_URL env var"
        assert self.supabase_url.startswith(
            ("http://", "https://")
        ), f"Bad Supabase Url: {self.supabase_url}"
        assert self.supabase_key is not None, "Set SUPABASE_KEY env var"
        
