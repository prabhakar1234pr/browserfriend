"""LLM integration module for BrowserFriend.

Provides AI-powered browsing insights using Google Gemini.
"""

from browserfriend.llm.analyzer import analyze_browsing_data, generate_insights
from browserfriend.llm.display import display_insights

__all__ = [
    "analyze_browsing_data",
    "generate_insights",
    "display_insights",
    "LLMError",
    "APIKeyError",
    "RateLimitError",
    "InsufficientDataError",
]


class LLMError(Exception):
    """Base exception for LLM operations."""

    pass


class APIKeyError(LLMError):
    """Invalid or missing API key."""

    pass


class RateLimitError(LLMError):
    """API rate limit exceeded."""

    pass


class InsufficientDataError(LLMError):
    """Not enough browsing data to analyze."""

    pass
