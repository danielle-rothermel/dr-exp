"""Priority system constants, classes, and utilities for job queue management."""

from enum import Enum
from typing import Dict, Any
from datetime import datetime, UTC


# Priority constants
PRIORITY_MIN = 0
PRIORITY_MAX = 1000
PRIORITY_DEFAULT = 100


class PriorityClass(Enum):
    """Predefined priority classes with named ranges.

    Each priority class defines a range of numeric priorities to make
    it easier for users to choose appropriate priority levels without
    needing to understand the full 0-1000 scale.
    """

    SYSTEM = (900, 1000)  # System maintenance, critical fixes
    URGENT = (700, 899)  # "Run one", deadline-driven experiments
    HIGH = (400, 699)  # Important experiments, time-sensitive
    NORMAL = (100, 399)  # Default range for regular experiments
    LOW = (0, 99)  # Background jobs, nice-to-have experiments

    @property
    def min_priority(self) -> int:
        """Minimum priority value for this class."""
        return self.value[0]

    @property
    def max_priority(self) -> int:
        """Maximum priority value for this class."""
        return self.value[1]

    @property
    def default_priority(self) -> int:
        """Default priority value for this class (midpoint of range)."""
        return (self.value[0] + self.value[1]) // 2

    def contains(self, priority: int) -> bool:
        """Check if a priority value falls within this class range.

        Parameters
        ----------
        priority : int
            Priority value to check.

        Returns
        -------
        bool
            True if priority is within this class range.
        """
        return self.min_priority <= priority <= self.max_priority

    @classmethod
    def from_priority(cls, priority: int) -> "PriorityClass":
        """Get the priority class that contains the given priority value.

        Parameters
        ----------
        priority : int
            Priority value to classify.

        Returns
        -------
        PriorityClass
            The priority class containing this value.

        Raises
        ------
        ValueError
            If priority is not within any valid priority class range.
        """
        for priority_class in cls:
            if priority_class.contains(priority):
                return priority_class
        raise ValueError(
            f"Invalid priority {priority}: must be between {cls.LOW.min_priority} and {cls.SYSTEM.max_priority}"
        )


def validate_priority(priority: int) -> int:
    """Validate a priority value is within the valid range.

    Parameters
    ----------
    priority : int
        Priority value to validate.

    Returns
    -------
    int
        The validated priority value.

    Raises
    ------
    ValueError
        If priority is not an integer or is outside the valid range (0-1000).
    """
    if not isinstance(priority, int):
        raise ValueError(f"Priority must be an integer, got {type(priority).__name__}")
    if not (PRIORITY_MIN <= priority <= PRIORITY_MAX):
        raise ValueError(
            f"Priority must be between {PRIORITY_MIN} and {PRIORITY_MAX}, got {priority}"
        )
    return priority


def get_priority_description(priority: int) -> str:
    """Get a human-readable description of a priority value.

    Parameters
    ----------
    priority : int
        Priority value to describe.

    Returns
    -------
    str
        Description string indicating priority level and class.

    Raises
    ------
    ValueError
        If priority is not an integer or is outside the valid range (0-1000).
    """
    validated_priority = validate_priority(priority)
    priority_class = PriorityClass.from_priority(validated_priority)
    return f"{validated_priority} ({priority_class.name.lower()})"


def calculate_age_boost(job: Dict[str, Any], max_boost: int = 200) -> int:
    """Calculate priority boost based on job age to prevent starvation.

    Jobs that have been waiting longer receive higher priority boosts
    to ensure they eventually get executed.

    Parameters
    ----------
    job : dict[str, Any]
        Job record containing 'created_at' timestamp.
    max_boost : int, optional
        Maximum boost amount to prevent runaway priority inflation,
        by default 200.

    Returns
    -------
    int
        Priority boost amount based on age (0 to max_boost).
    """
    created_at_str = job.get("created_at")
    if not created_at_str:
        return 0

    try:
        # Parse timestamp (handle both with and without 'Z' suffix)
        created_at_str = created_at_str.rstrip("Z")
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))

        # Calculate age in hours
        age_seconds = (datetime.now(UTC) - created_at).total_seconds()
        age_hours = age_seconds / 3600

        # Apply boost: +10 priority per hour, capped at max_boost
        boost = min(int(age_hours * 10), max_boost)
        return boost

    except (ValueError, TypeError):
        # Invalid timestamp format
        return 0


def calculate_failure_penalty(job: Dict[str, Any], max_penalty: int = 200) -> int:
    """Calculate priority penalty based on job failure history.

    Jobs that have failed multiple times receive lower priority to
    prevent repeatedly failing jobs from blocking the queue.

    Parameters
    ----------
    job : dict[str, Any]
        Job record containing 'retry_index' or failure count.
    max_penalty : int, optional
        Maximum penalty amount, by default 200.

    Returns
    -------
    int
        Priority penalty amount (negative value, 0 to -max_penalty).
    """
    retry_count: int = job.get("retry_index", 0)

    # Apply penalty: -50 priority per retry, capped at max_penalty
    penalty = min(retry_count * 50, max_penalty)
    return -penalty


def apply_priority_strategy(
    job: Dict[str, Any], strategy: str = "age_boost", **strategy_params: Any
) -> int:
    """Apply a priority adjustment strategy to a job.

    Parameters
    ----------
    job : dict[str, Any]
        Job record to analyze.
    strategy : str, optional
        Strategy name ("age_boost", "failure_penalty", "combined"),
        by default "age_boost".
    **strategy_params
        Additional parameters for the strategy.

    Returns
    -------
    int
        Priority adjustment amount (positive for boost, negative for penalty).
    """
    if strategy == "age_boost":
        return calculate_age_boost(job, **strategy_params)
    elif strategy == "failure_penalty":
        return calculate_failure_penalty(job, **strategy_params)
    elif strategy == "combined":
        age_boost = calculate_age_boost(job, strategy_params.get("max_boost", 200))
        failure_penalty = calculate_failure_penalty(
            job, strategy_params.get("max_penalty", 200)
        )
        return age_boost + failure_penalty
    else:
        raise ValueError(f"Unknown priority strategy: {strategy}")


def get_effective_priority(job: Dict[str, Any], strategy: str = "combined") -> int:
    """Calculate the effective priority for a job including adjustments.

    Parameters
    ----------
    job : dict[str, Any]
        Job record to analyze.
    strategy : str, optional
        Priority strategy to apply, by default "combined".

    Returns
    -------
    int
        Effective priority value after applying strategy adjustments.
    """
    base_priority = job["priority"]  # Fail fast if priority missing
    adjustment = apply_priority_strategy(job, strategy)
    effective_priority = validate_priority(base_priority + adjustment)

    return effective_priority


__all__ = [
    "PRIORITY_MIN",
    "PRIORITY_MAX",
    "PRIORITY_DEFAULT",
    "PriorityClass",
    "validate_priority",
    "get_priority_description",
    "calculate_age_boost",
    "calculate_failure_penalty",
    "apply_priority_strategy",
    "get_effective_priority",
]
