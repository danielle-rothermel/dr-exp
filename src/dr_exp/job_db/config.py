"""Configuration for JobDB instances."""

import os
from dataclasses import dataclass
from typing import Optional


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
    storage_path: str = "./storage"
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        self.validate()

    def validate(self) -> None:
        """Validate configuration settings.

        Raises
        ------
        ValueError
            If configuration is invalid (e.g., missing Supabase credentials
            for supabase_remote mode, invalid URL format).
        """
        # Validate mode
        valid_modes = ["files_local", "supabase_local", "supabase_remote"]
        if self.mode not in valid_modes:
            raise ValueError(
                f"Invalid mode '{self.mode}'. Must be one of: {valid_modes}"
            )

        # Read Supabase credentials from environment variables
        if self.mode in ["supabase_remote", "supabase_local"]:
            if not self.supabase_url:
                self.supabase_url = os.getenv("SUPABASE_URL")
            if not self.supabase_key:
                self.supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv(
                    "SUPABASE_KEY"
                )

        # Validate Supabase configuration
        if self.mode in ["supabase_remote", "supabase_local"]:
            if not self.supabase_url or not self.supabase_key:
                raise ValueError(
                    f"Supabase URL and Key required for {self.mode} mode. "
                    f"Set SUPABASE_URL and SUPABASE_KEY environment variables."
                )
            if not self.supabase_url.startswith(("http://", "https://")):
                raise ValueError("Invalid Supabase URL format")

        # Set default storage path if not provided
        if self.storage_path == "./storage":
            self.storage_path = os.path.join(self.base_path, "storage")

        # Ensure paths are absolute for consistency
        self.base_path = os.path.abspath(self.base_path)
        self.storage_path = os.path.abspath(self.storage_path)

    def is_supabase_mode(self) -> bool:
        """Check if configuration is for Supabase mode.

        Returns
        -------
        bool
            True if mode is "supabase_remote" or "supabase_local" and Supabase credentials are available.
        """
        return self.mode in ["supabase_remote", "supabase_local"] and bool(
            self.supabase_url and self.supabase_key
        )
