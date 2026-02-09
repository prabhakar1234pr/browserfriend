"""Rich terminal display for browsing insights."""

import logging
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)
console = Console()


def _format_seconds(seconds: float) -> str:
    """Format seconds into human-readable string."""
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


def _make_progress_bar(value: int, width: int = 20) -> str:
    """Create a simple text-based progress bar."""
    filled = round(value / 100 * width)
    empty = width - filled
    return "\u2588" * filled + "\u2591" * empty


def display_insights(insights: dict) -> None:
    """Display insights in terminal with Rich formatting.

    Shows session summary, statistics table, category breakdown,
    productivity score, AI summary, and recommendations.

    Args:
        insights: Dictionary from generate_insights()
    """
    stats = insights.get("stats", {})
    categories = insights.get("categories", {})
    summary_text = insights.get("summary", "")
    patterns = insights.get("patterns", [])
    prod_score = insights.get("productivity_score", 0)
    prod_breakdown = insights.get("productivity_breakdown", {})
    recommendations = insights.get("recommendations", [])
    time_insights = insights.get("time_insights", {})
    used_fallback = insights.get("used_fallback", False)

    today = datetime.now().strftime("%B %d, %Y")

    # Header panel
    header_text = Text()
    header_text.append("BrowserFriend Session Insights\n", style="bold cyan")
    header_text.append(today, style="dim")
    if used_fallback:
        header_text.append("\n(Rule-based analysis - LLM unavailable)", style="yellow")
    console.print(Panel(header_text, border_style="cyan", expand=True))
    console.print()

    # Session overview table
    console.print("[bold]Session Overview[/bold]")
    console.print("\u2501" * 52)

    overview_table = Table(show_header=False, box=None, padding=(0, 2))
    overview_table.add_column("Label", style="dim", width=22)
    overview_table.add_column("Value", style="bold")
    overview_table.add_row("Total Time", _format_seconds(stats.get("total_time", 0)))
    overview_table.add_row("Total Visits", str(stats.get("total_visits", 0)) + " pages")
    overview_table.add_row("Unique Domains", str(stats.get("unique_domains", 0)) + " sites")
    overview_table.add_row("Session Duration", _format_seconds(stats.get("session_duration", 0)))
    console.print(overview_table)
    console.print()

    # Top domains table
    top_domains = stats.get("top_domains", [])
    if top_domains:
        console.print("[bold]Top Domains by Time[/bold]")
        console.print("\u2501" * 52)

        domain_table = Table(show_header=True, box=None, padding=(0, 1))
        domain_table.add_column("#", style="dim", width=3)
        domain_table.add_column("Domain", style="bold", min_width=25)
        domain_table.add_column("Time", justify="right", width=10)
        domain_table.add_column("%", justify="right", width=6)
        domain_table.add_column("Category", style="cyan", width=15)

        for i, d in enumerate(top_domains[:10], 1):
            cat = categories.get(d["domain"], "other")
            domain_table.add_row(
                str(i),
                d["domain"],
                _format_seconds(d["total_time"]),
                f"{d['percentage']:.1f}%",
                f"[{_category_color(cat)}]{cat}[/]",
            )
        console.print(domain_table)
        console.print()

    # Productivity score
    console.print("[bold]Productivity Score: {}/100[/bold]".format(prod_score))
    console.print("\u2501" * 52)

    prod_pct = prod_breakdown.get("productive_time", 0)
    neut_pct = prod_breakdown.get("neutral_time", 0)
    dist_pct = prod_breakdown.get("distracting_time", 0)

    console.print(f"  [green]{_make_progress_bar(prod_pct)}[/green]  Productive: {prod_pct}%")
    console.print(f"  [yellow]{_make_progress_bar(neut_pct)}[/yellow]  Neutral: {neut_pct}%")
    console.print(f"  [red]{_make_progress_bar(dist_pct)}[/red]  Distracting: {dist_pct}%")
    console.print()

    # AI Summary
    if summary_text:
        console.print("[bold]AI Summary[/bold]")
        console.print("\u2501" * 52)
        console.print(summary_text)
        console.print()

    # Patterns
    if patterns:
        console.print("[bold]Patterns Detected[/bold]")
        console.print("\u2501" * 52)
        for pattern in patterns:
            console.print(f"  [dim]\u2022[/dim] {pattern}")
        console.print()

    # Recommendations
    if recommendations:
        console.print("[bold]Personalized Recommendations[/bold]")
        console.print("\u2501" * 52)
        for rec in recommendations:
            console.print(f"  [dim]\u2022[/dim] {rec}")
        console.print()

    # Time insights
    if time_insights:
        console.print("[bold]Time Insights[/bold]")
        console.print("\u2501" * 52)
        most_active = time_insights.get("most_active_period", "unknown")
        console.print(f"  Most Active:  {most_active}")
        focus = time_insights.get("focus_hours", [])
        if focus:
            console.print(f"  Peak Focus:   {', '.join(focus)}")
        distraction = time_insights.get("distraction_hours", [])
        if distraction:
            console.print(f"  Distraction:  {', '.join(distraction)}")
        console.print()

    # Time distribution
    td = stats.get("time_distribution", {})
    if any(td.values()):
        console.print("[bold]Time Distribution[/bold]")
        console.print("\u2501" * 52)
        for period in ["morning", "afternoon", "evening", "night"]:
            label = {
                "morning": "Morning   (6am-12pm)",
                "afternoon": "Afternoon (12pm-6pm)",
                "evening": "Evening   (6pm-12am)",
                "night": "Night     (12am-6am)",
            }[period]
            console.print(f"  {label}: {_format_seconds(td.get(period, 0))}")
        console.print()

    console.print("[green bold]Dashboard generated successfully![/green bold]")


def _category_color(category: str) -> str:
    """Return a Rich color name for a category."""
    colors = {
        "development": "green",
        "productivity": "blue",
        "communication": "cyan",
        "social": "magenta",
        "entertainment": "yellow",
        "news": "white",
        "shopping": "red",
        "other": "dim",
    }
    return colors.get(category, "dim")
