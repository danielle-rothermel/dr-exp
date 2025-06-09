"""Tests for CLI validation utilities."""

import pytest

from dr_exp.utils.cli_validation import (
    ValidationError,
    validate_priority,
    validate_job_id,
    validate_positive_int,
    validate_job_statuses,
    validate_config_overrides,
)


def test_validate_priority() -> None:
    """Test priority validation."""
    # Valid priorities
    assert validate_priority(0) == 0
    assert validate_priority(500) == 500
    assert validate_priority(1000) == 1000

    # Invalid priorities
    with pytest.raises(ValidationError, match="Priority must be between"):
        validate_priority(-1)

    with pytest.raises(ValidationError, match="Priority must be between"):
        validate_priority(1001)

    with pytest.raises(ValidationError, match="Priority must be an integer"):
        validate_priority("invalid")  # type: ignore[arg-type]


def test_validate_job_id() -> None:
    """Test job ID validation."""
    # Valid job IDs (must be at least 8 characters)
    assert validate_job_id("job12345") == "job12345"
    assert validate_job_id("  job12345  ") == "job12345"  # Should strip whitespace

    # Invalid job IDs
    with pytest.raises(ValidationError, match="Job ID cannot be empty"):
        validate_job_id("")

    with pytest.raises(ValidationError, match="Job ID cannot be empty"):
        validate_job_id("   ")

    with pytest.raises(ValidationError, match="Job ID must be at least 8 characters"):
        validate_job_id("short")

    with pytest.raises(ValidationError, match="Job ID must be a string"):
        validate_job_id(123)  # type: ignore[arg-type]


def test_validate_positive_int() -> None:
    """Test positive integer validation."""
    # Valid values
    assert validate_positive_int(1, "test") == 1
    assert validate_positive_int(100, "test") == 100

    # Invalid values
    with pytest.raises(ValidationError, match="test must be positive"):
        validate_positive_int(0, "test")

    with pytest.raises(ValidationError, match="test must be positive"):
        validate_positive_int(-1, "test")

    with pytest.raises(ValidationError, match="test must be an integer"):
        validate_positive_int("invalid", "test")  # type: ignore[arg-type]


def test_validate_job_statuses() -> None:
    """Test job status validation."""
    # Valid statuses
    assert validate_job_statuses(["queued"]) == ["queued"]
    assert validate_job_statuses(["queued", "running"]) == ["queued", "running"]

    # Invalid statuses
    with pytest.raises(ValidationError, match="Status list cannot be empty"):
        validate_job_statuses([])

    with pytest.raises(ValidationError, match="Invalid job statuses"):
        validate_job_statuses(["invalid"])


def test_validate_config_overrides() -> None:
    """Test config override validation."""
    # Valid overrides
    assert validate_config_overrides("") == []
    assert validate_config_overrides("key=value") == ["key=value"]
    assert validate_config_overrides("key1=value1,key2=value2") == [
        "key1=value1",
        "key2=value2",
    ]

    # Invalid overrides
    with pytest.raises(ValidationError, match="Invalid override format"):
        validate_config_overrides("invalid_format")

    with pytest.raises(ValidationError, match="Empty key in override"):
        validate_config_overrides("=value")
