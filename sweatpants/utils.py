"""Utility functions for Sweatpants."""

import re


def parse_duration(duration: str) -> int:
    """Parse duration string to seconds.

    Args:
        duration: Duration string like '30m', '2h', '24h', '7d'

    Returns:
        Duration in seconds

    Raises:
        ValueError: If format is invalid
    """
    match = re.match(r"^(\d+)(m|h|d)$", duration)
    if not match:
        raise ValueError(f"Invalid duration format: {duration}. Use: 30m, 2h, 24h, 7d")

    value, unit = int(match.group(1)), match.group(2)
    multipliers = {"m": 60, "h": 3600, "d": 86400}
    return value * multipliers[unit]
