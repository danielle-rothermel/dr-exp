"""Centralized CLI configuration constants."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CLIDefaults:
    """Default values for CLI arguments."""
    
    # Manager configuration
    GPUS_PER_NODE = 1
    WORKERS_PER_GPU = 1
    HEARTBEAT_TIMEOUT = 60
    IDLE_TIMEOUT_MINS = 30
    
    # Priority system
    DEFAULT_PRIORITY = 100
    MIN_PRIORITY = 0
    MAX_PRIORITY = 1000
    PRIORITY_BOOST_AMOUNT = 100
    RUN_ONE_PRIORITY = 850
    
    # Job listing
    DEFAULT_JOB_LIMIT = 20
    DEFAULT_JOB_STATUS = ["queued"]
    
    # Job reaping
    DEFAULT_MAX_AGE_MINS = 60
    
    # Multiprocessing
    DEFAULT_START_METHOD = "fork"


# Export singleton instance
CLI_DEFAULTS = CLIDefaults()