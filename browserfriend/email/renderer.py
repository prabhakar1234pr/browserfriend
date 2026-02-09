"""Dashboard email template rendering with Jinja2."""

import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from browserfriend.email.utils import format_duration, get_category_color

logger = logging.getLogger(__name__)


def render_dashboard_email(insights: dict, stats: dict, user_email: str) -> str:
    """Render dashboard HTML email from template.

    Args:
        insights: Full insights dict from generate_insights()
        stats: The stats sub-dict (insights['stats'])
        user_email: Recipient email

    Returns:
        Complete HTML string ready to send
    """
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    env.filters["format_duration"] = format_duration
    env.filters["category_color"] = get_category_color
    template = env.get_template("dashboard_email.html")

    # Prepare template variables
    top_domains = stats.get("top_domains", [])
    categories = insights.get("categories", {})
    productivity_breakdown = insights.get("productivity_breakdown", {})
    time_distribution = stats.get("time_distribution", {})
    time_insights = insights.get("time_insights", {})

    html = template.render(
        email=user_email,
        date=datetime.now().strftime("%B %d, %Y"),
        session_id=insights.get("session_id", ""),
        total_time=format_duration(stats.get("total_time", 0)),
        total_visits=stats.get("total_visits", 0),
        unique_domains=stats.get("unique_domains", 0),
        productivity_score=insights.get("productivity_score", 0),
        productivity_breakdown=productivity_breakdown,
        summary=insights.get("summary", ""),
        top_domains=top_domains,
        categories=categories,
        patterns=insights.get("patterns", []),
        recommendations=insights.get("recommendations", []),
        time_insights=time_insights,
        time_distribution=time_distribution,
        generated_at=insights.get("generated_at", datetime.now().isoformat()),
        format_duration=format_duration,
        get_category_color=get_category_color,
    )

    logger.info("Dashboard email rendered (%d chars)", len(html))
    return html
