"""Utility functions for the email module."""

import logging

logger = logging.getLogger(__name__)


def format_duration(seconds: float) -> str:
    """Format seconds to human-readable time string.

    Args:
        seconds: Number of seconds

    Returns:
        Formatted string like '2h 15m' or '45m'
    """
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def calculate_percentage(part: float, total: float) -> float:
    """Calculate percentage with proper rounding.

    Args:
        part: The part value
        total: The total value

    Returns:
        Rounded percentage value
    """
    if total == 0:
        return 0.0
    return round((part / total) * 100, 1)


def get_category_color(category: str) -> str:
    """Get hex color code for a browsing category.

    Args:
        category: Category name (e.g., 'development', 'social')

    Returns:
        Hex color string
    """
    colors = {
        "productivity": "#4CAF50",
        "development": "#2196F3",
        "social": "#FF9800",
        "entertainment": "#E91E63",
        "news": "#9C27B0",
        "communication": "#00BCD4",
        "shopping": "#FFC107",
        "other": "#9E9E9E",
    }
    return colors.get(category.lower(), "#9E9E9E")
