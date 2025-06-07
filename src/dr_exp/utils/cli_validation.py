"""Input validation utilities for CLI commands."""

import re
from typing import List, Any
from pathlib import Path

from dr_exp.utils.cli_config import CLI_DEFAULTS


class ValidationError(Exception):
    """Raised when CLI input validation fails."""
    pass


def validate_priority(priority: int) -> int:
    """Validate priority is in valid range.
    
    Parameters
    ----------
    priority : int
        Priority value to validate
        
    Returns
    -------
    int
        Validated priority
        
    Raises
    ------
    ValidationError
        If priority is out of range
    """
    if not isinstance(priority, int):
        raise ValidationError(f"Priority must be an integer, got {type(priority).__name__}")
    
    if not (CLI_DEFAULTS.MIN_PRIORITY <= priority <= CLI_DEFAULTS.MAX_PRIORITY):
        raise ValidationError(
            f"Priority must be between {CLI_DEFAULTS.MIN_PRIORITY} and {CLI_DEFAULTS.MAX_PRIORITY}, got {priority}"
        )
    
    return priority


def validate_job_id(job_id: str) -> str:
    """Validate job ID format.
    
    Parameters
    ----------
    job_id : str
        Job ID to validate
        
    Returns
    -------
    str
        Validated job ID
        
    Raises
    ------
    ValidationError
        If job ID format is invalid
    """
    if not isinstance(job_id, str):
        raise ValidationError(f"Job ID must be a string, got {type(job_id).__name__}")
    
    if not job_id.strip():
        raise ValidationError("Job ID cannot be empty")
    
    # Basic UUID format check (flexible to support different ID formats)
    job_id = job_id.strip()
    if len(job_id) < 8:
        raise ValidationError("Job ID must be at least 8 characters long")
    
    return job_id


def validate_positive_int(value: int, name: str) -> int:
    """Validate that a value is a positive integer.
    
    Parameters
    ----------
    value : int
        Value to validate
    name : str
        Name of the parameter for error messages
        
    Returns
    -------
    int
        Validated value
        
    Raises
    ------
    ValidationError
        If value is not positive
    """
    if not isinstance(value, int):
        raise ValidationError(f"{name} must be an integer, got {type(value).__name__}")
    
    if value <= 0:
        raise ValidationError(f"{name} must be positive, got {value}")
    
    return value


def validate_job_statuses(statuses: List[str]) -> List[str]:
    """Validate job status filter list.
    
    Parameters
    ----------
    statuses : List[str]
        List of job statuses to validate
        
    Returns
    -------
    List[str]
        Validated status list
        
    Raises
    ------
    ValidationError
        If any status is invalid
    """
    valid_statuses = {"queued", "running", "completed", "failed", "killed"}
    
    if not statuses:
        raise ValidationError("Status list cannot be empty")
    
    invalid_statuses = [s for s in statuses if s not in valid_statuses]
    if invalid_statuses:
        raise ValidationError(
            f"Invalid job statuses: {invalid_statuses}. "
            f"Valid statuses are: {sorted(valid_statuses)}"
        )
    
    return statuses


def validate_file_path(path: str, must_exist: bool = True) -> Path:
    """Validate file path.
    
    Parameters
    ----------
    path : str
        File path to validate
    must_exist : bool, optional
        Whether the path must exist, by default True
        
    Returns
    -------
    Path
        Validated path object
        
    Raises
    ------
    ValidationError
        If path is invalid or doesn't exist when required
    """
    if not isinstance(path, str):
        raise ValidationError(f"Path must be a string, got {type(path).__name__}")
    
    if not path.strip():
        raise ValidationError("Path cannot be empty")
    
    path_obj = Path(path.strip())
    
    if must_exist and not path_obj.exists():
        raise ValidationError(f"Path does not exist: {path}")
    
    return path_obj


def validate_config_overrides(overrides: str) -> List[str]:
    """Validate and parse config override string.
    
    Parameters
    ----------
    overrides : str
        Comma-separated config overrides in format "key=value,key2=value2"
        
    Returns
    -------
    List[str]
        List of individual overrides
        
    Raises
    ------
    ValidationError
        If override format is invalid
    """
    if not overrides.strip():
        return []
    
    override_list = []
    for override in overrides.split(","):
        override = override.strip()
        if not override:
            continue
            
        if "=" not in override:
            raise ValidationError(f"Invalid override format '{override}'. Expected 'key=value'")
        
        key, value = override.split("=", 1)
        if not key.strip():
            raise ValidationError(f"Empty key in override '{override}'")
        
        override_list.append(override)
    
    return override_list