"""Global pytest configuration and fixtures."""

import pytest
from typing import Any, Dict, Optional


def make_wrapped_config(
    config_dict: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a properly wrapped config for tests that simulate the full upload workflow.

    This function creates the config structure that would normally be created
    by the config upload process.

    Args:
        config_dict: The training configuration dictionary
        metadata: Optional metadata dict, defaults to test metadata

    Returns:
        Dict with {"config": config_dict, "metadata": metadata} structure
    """
    if metadata is None:
        metadata = {
            "cluster_name": "test_cluster",
            "description": "test config",
            "interface_version": None,
            "code_version": None,
        }

    return {"config": config_dict, "metadata": metadata}


# Pytest markers for organizing tests
def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "supabase: mark test as requiring local Supabase"
    )
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "fast: mark test as fast running")
    config.addinivalue_line(
        "markers", "concurrency: mark test as testing concurrent behavior"
    )
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "edge_case: mark test for edge case scenarios")
    config.addinivalue_line(
        "markers", "timeout: mark test as including timeouts (very slow)"
    )
