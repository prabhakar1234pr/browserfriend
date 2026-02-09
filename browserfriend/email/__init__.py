"""Email module for BrowserFriend.

Provides email delivery of AI-generated dashboards via Resend.
"""

from browserfriend.email.renderer import render_dashboard_email
from browserfriend.email.sender import send_dashboard_email
from browserfriend.email.utils import calculate_percentage, format_duration, get_category_color

__all__ = [
    "send_dashboard_email",
    "render_dashboard_email",
    "format_duration",
    "calculate_percentage",
    "get_category_color",
]
