"""Prompt templates for LLM-powered browsing insights."""

ANALYSIS_PROMPT = """You are analyzing a user's browsing session to provide insights.

Session Overview:
- Total Time: {total_time_formatted}
- Total Visits: {total_visits}
- Unique Domains: {unique_domains}
- Duration: {session_duration_formatted}

Top Domains by Time:
{top_domains_text}

Time Distribution:
- Morning (6am-12pm): {morning_time}
- Afternoon (12pm-6pm): {afternoon_time}
- Evening (6pm-12am): {evening_time}
- Night (12am-6am): {night_time}

Visit Timeline (chronological):
{timeline_text}

Please provide a comprehensive analysis in JSON format with these fields:

{{
  "categories": {{
    "domain1": "category",
    "domain2": "category"
  }},
  "summary": "2-3 paragraph narrative summary of browsing habits",
  "patterns": [
    "Pattern 1 you observed",
    "Pattern 2 you observed",
    "Pattern 3 you observed"
  ],
  "productivity_score": 75,
  "productivity_breakdown": {{
    "productive_time": 60,
    "neutral_time": 25,
    "distracting_time": 15
  }},
  "recommendations": [
    "Recommendation 1",
    "Recommendation 2",
    "Recommendation 3"
  ],
  "time_insights": {{
    "most_active_period": "afternoon",
    "focus_hours": ["2pm-4pm"],
    "distraction_hours": ["8pm-10pm"]
  }}
}}

Categories should be one of:
- productivity (work tools, documentation, learning)
- development (coding, GitHub, Stack Overflow)
- communication (email, Slack, messaging)
- social (Twitter, Reddit, social media)
- entertainment (YouTube, Netflix, gaming)
- news (news sites, blogs)
- shopping (e-commerce, product research)
- other

Provide actionable, personalized recommendations based on their actual behavior.
Respond ONLY with the JSON object, no extra text or markdown fences.
"""


def format_analysis_prompt(stats: dict) -> str:
    """Format the analysis prompt with actual session data.

    Args:
        stats: Dictionary from analyze_browsing_data()

    Returns:
        Formatted prompt string ready for LLM
    """
    # Format top domains text
    top_domains_lines = []
    for i, domain_info in enumerate(stats.get("top_domains", []), 1):
        top_domains_lines.append(
            f"{i}. {domain_info['domain']} - {_format_seconds(domain_info['total_time'])} "
            f"({domain_info['percentage']:.1f}%)"
        )
    top_domains_text = "\n".join(top_domains_lines) if top_domains_lines else "No data"

    # Format timeline text
    timeline_lines = []
    for visit in stats.get("visit_timeline", [])[:20]:  # Limit to 20 visits
        timeline_lines.append(
            f"- {visit['domain']} | {visit.get('title', 'N/A')} | "
            f"{_format_seconds(visit['duration'])}"
        )
    timeline_text = "\n".join(timeline_lines) if timeline_lines else "No data"

    # Format time distribution
    time_dist = stats.get("time_distribution", {})

    return ANALYSIS_PROMPT.format(
        total_time_formatted=_format_seconds(stats.get("total_time", 0)),
        total_visits=stats.get("total_visits", 0),
        unique_domains=stats.get("unique_domains", 0),
        session_duration_formatted=_format_seconds(stats.get("session_duration", 0)),
        top_domains_text=top_domains_text,
        morning_time=_format_seconds(time_dist.get("morning", 0)),
        afternoon_time=_format_seconds(time_dist.get("afternoon", 0)),
        evening_time=_format_seconds(time_dist.get("evening", 0)),
        night_time=_format_seconds(time_dist.get("night", 0)),
        timeline_text=timeline_text,
    )


def _format_seconds(seconds: float) -> str:
    """Format seconds into human-readable string.

    Args:
        seconds: Number of seconds

    Returns:
        Formatted string like '1h 23m' or '45m 30s'
    """
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    remaining_secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {remaining_secs}s" if remaining_secs else f"{minutes}m"
    hours = minutes // 60
    remaining_mins = minutes % 60
    if remaining_mins:
        return f"{hours}h {remaining_mins}m"
    return f"{hours}h"
