"""GPU discovery utilities for the experiment management system."""

import os
from typing import List


def discover_gpus(gpus_per_node: int) -> List[str]:
    """Discover available GPUs from environment.
    
    Parameters
    ----------
    gpus_per_node : int
        Number of GPUs to assume if CUDA_VISIBLE_DEVICES is not set
        
    Returns
    -------
    List[str]
        List of GPU IDs as strings
        
    Raises
    ------
    ValueError
        If gpus_per_node is not positive
    """
    if gpus_per_node <= 0:
        raise ValueError("gpus_per_node must be positive")
    
    env = os.environ.get("CUDA_VISIBLE_DEVICES")
    if env:
        gpu_ids = [g.strip() for g in env.split(",") if g.strip()]
        if not gpu_ids:
            raise ValueError("CUDA_VISIBLE_DEVICES is set but contains no valid GPU IDs")
        return gpu_ids
    
    return [str(i) for i in range(gpus_per_node)]


def validate_gpu_ids(gpu_ids: List[str]) -> None:
    """Validate that GPU IDs are properly formatted.
    
    Parameters
    ----------
    gpu_ids : List[str]
        List of GPU IDs to validate
        
    Raises
    ------
    ValueError
        If any GPU ID is invalid
    """
    if not gpu_ids:
        raise ValueError("GPU list cannot be empty")
    
    for gpu_id in gpu_ids:
        if not isinstance(gpu_id, str):
            raise ValueError(f"GPU ID must be string, got {type(gpu_id)}")
        
        # Check if it's a valid integer string
        try:
            int(gpu_id)
        except ValueError:
            raise ValueError(f"GPU ID '{gpu_id}' is not a valid integer")