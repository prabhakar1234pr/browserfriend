"""Browsing data analysis and AI insight generation using Google Gemini.

Queries session data from the database, formats statistics, and calls
the Gemini API to produce categorised, narrative insights.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from browserfriend.config import get_config
from browserfriend.llm.prompts import format_analysis_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fallback domain categories used when LLM is unavailable
# ---------------------------------------------------------------------------

# Keyword-based fallback categorisation (used only when LLM is unavailable)
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "development": [
        "github",
        "gitlab",
        "bitbucket",
        "stackoverflow",
        "stackexchange",
        "docs.",
        "pypi",
        "npm",
        "crates",
        "codepen",
        "replit",
        "leetcode",
        "hackerrank",
        "vercel",
        "netlify",
        "heroku",
    ],
    "productivity": [
        "google.com",
        "notion",
        "figma",
        "docs.google",
        "drive.google",
        "chatgpt",
        "claude",
        "udemy",
        "coursera",
        "edx",
        "khanacademy",
        "trello",
        "jira",
        "confluence",
        "miro",
    ],
    "communication": [
        "gmail",
        "mail.",
        "outlook",
        "slack",
        "discord",
        "teams",
        "zoom",
        "meet.google",
    ],
    "social": [
        "twitter",
        "x.com",
        "facebook",
        "instagram",
        "tiktok",
        "snapchat",
        "reddit",
        "threads",
    ],
    "entertainment": [
        "youtube",
        "netflix",
        "twitch",
        "spotify",
        "hulu",
        "disney",
        "primevideo",
        "gaming",
    ],
    "news": ["news", "cnn", "bbc", "nytimes", "reuters", "medium.com", "techcrunch", "theverge"],
    "shopping": ["amazon", "ebay", "shopify", "etsy", "walmart", "flipkart"],
}


def _categorise_domain(domain: str) -> str:
    """Categorise a domain using keyword matching (fallback only)."""
    domain_lower = domain.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in domain_lower for kw in keywords):
            return category
    return "other"


# ---------------------------------------------------------------------------
# Data analysis – pure database queries, no LLM needed
# ---------------------------------------------------------------------------


def analyze_browsing_data(session_id: str) -> dict:
    """Query database for session data and prepare statistics.

    Args:
        session_id: UUID of the browsing session to analyze

    Returns:
        Dictionary with session statistics ready for prompt formatting.

    Raises:
        ValueError: If the session is not found.
    """
    from browserfriend.database import BrowsingSession, PageVisit, get_session_factory

    logger.info("Analyzing browsing data for session: %s", session_id)

    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        # Fetch session
        browsing_session = (
            session.query(BrowsingSession).filter(BrowsingSession.session_id == session_id).first()
        )
        if browsing_session is None:
            raise ValueError(f"Session not found: {session_id}")

        # Fetch all visits ordered chronologically
        visits = (
            session.query(PageVisit)
            .filter(PageVisit.session_id == session_id)
            .order_by(PageVisit.start_time.asc())
            .all()
        )

        if not visits:
            logger.warning("Session %s has no page visits", session_id)

        # Total time across all visits
        total_time = sum(v.duration_seconds or 0 for v in visits)
        total_visits = len(visits)
        unique_domains = len({v.domain for v in visits})

        # Session duration (start to end)
        session_duration = 0.0
        if browsing_session.duration:
            session_duration = browsing_session.duration
        elif browsing_session.end_time and browsing_session.start_time:
            start = browsing_session.start_time
            end = browsing_session.end_time
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            session_duration = (end - start).total_seconds()

        # Aggregate time per domain
        domain_stats: dict[str, dict] = {}
        for v in visits:
            d = v.domain
            if d not in domain_stats:
                domain_stats[d] = {"domain": d, "visits": 0, "total_time": 0.0}
            domain_stats[d]["visits"] += 1
            domain_stats[d]["total_time"] += v.duration_seconds or 0

        for d in domain_stats.values():
            d["avg_time"] = d["total_time"] / d["visits"] if d["visits"] else 0
            d["percentage"] = (d["total_time"] / total_time * 100) if total_time else 0

        # Top domains by time
        sorted_domains = sorted(domain_stats.values(), key=lambda x: x["total_time"], reverse=True)
        top_domains = sorted_domains[:10]

        # Visit timeline
        visit_timeline = []
        for v in visits:
            visit_timeline.append(
                {
                    "url": v.url,
                    "domain": v.domain,
                    "title": v.title or "",
                    "duration": v.duration_seconds or 0,
                    "timestamp": (v.start_time.isoformat() if v.start_time else ""),
                }
            )

        # Time distribution by time of day
        time_distribution = {"morning": 0, "afternoon": 0, "evening": 0, "night": 0}
        for v in visits:
            if v.start_time is None:
                continue
            hour = v.start_time.hour
            dur = v.duration_seconds or 0
            if 6 <= hour < 12:
                time_distribution["morning"] += dur
            elif 12 <= hour < 18:
                time_distribution["afternoon"] += dur
            elif 18 <= hour < 24:
                time_distribution["evening"] += dur
            else:
                time_distribution["night"] += dur

        result = {
            "session_id": session_id,
            "total_time": total_time,
            "total_visits": total_visits,
            "unique_domains": unique_domains,
            "session_duration": session_duration,
            "domains": list(domain_stats.values()),
            "top_domains": top_domains,
            "visit_timeline": visit_timeline,
            "time_distribution": time_distribution,
        }
        logger.info(
            "Analysis complete: %d visits, %d domains, %.0fs total time",
            total_visits,
            unique_domains,
            total_time,
        )
        return result
    finally:
        session.close()


# ---------------------------------------------------------------------------
# LLM-powered insight generation
# ---------------------------------------------------------------------------


def _get_gemini_client():
    """Initialise and return the Google GenAI client.

    Raises:
        browserfriend.llm.APIKeyError: If the API key is missing.
    """
    from browserfriend.llm import APIKeyError

    config = get_config()
    api_key = config.google_api_key or config.gemini_api_key
    if not api_key or api_key == "your_google_api_key_here":
        raise APIKeyError(
            "Google API key not configured. "
            "Set GOOGLE_API_KEY or GEMINI_API_KEY in your .env file. "
            "Get a key at https://makersuite.google.com/app/apikey"
        )

    from google import genai

    client = genai.Client(api_key=api_key)
    logger.debug("Google GenAI client initialised")
    return client


def _call_gemini_with_retry(prompt: str, max_retries: int = 3, timeout: int = 30) -> str:
    """Call Gemini API with retry logic.

    Args:
        prompt: The formatted prompt string
        max_retries: Maximum retry attempts
        timeout: Timeout in seconds per attempt

    Returns:
        Raw text response from Gemini

    Raises:
        browserfriend.llm.RateLimitError: If rate limited after all retries.
        browserfriend.llm.LLMError: On other API failures.
    """
    from browserfriend.llm import LLMError, RateLimitError

    client = _get_gemini_client()
    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Gemini API call attempt %d/%d", attempt, max_retries)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            text = response.text.strip()
            logger.info("Gemini API response received (%d chars)", len(text))
            return text
        except Exception as exc:
            last_error = exc
            exc_str = str(exc).lower()
            logger.warning("Gemini API attempt %d failed: %s", attempt, exc)

            if "rate" in exc_str and "limit" in exc_str:
                if attempt == max_retries:
                    raise RateLimitError(
                        "Gemini API rate limit exceeded. Please wait and try again."
                    ) from exc
                wait = 2**attempt
                logger.info("Rate limited – waiting %ds before retry", wait)
                time.sleep(wait)
                continue

            if "api key" in exc_str or "authenticate" in exc_str:
                from browserfriend.llm import APIKeyError

                raise APIKeyError(f"Gemini API authentication failed: {exc}") from exc

            if attempt < max_retries:
                wait = 2**attempt
                logger.info("Retrying in %ds", wait)
                time.sleep(wait)
            else:
                raise LLMError(
                    f"Gemini API call failed after {max_retries} attempts: {exc}"
                ) from exc

    # Should never reach here, but just in case
    raise LLMError(f"Gemini API call failed: {last_error}")


def _parse_llm_response(raw_text: str) -> dict:
    """Parse the JSON response from the LLM.

    Handles markdown code fences and minor formatting issues.

    Args:
        raw_text: Raw text from LLM

    Returns:
        Parsed dictionary

    Raises:
        browserfriend.llm.LLMError: If the response cannot be parsed.
    """
    from browserfriend.llm import LLMError

    text = raw_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
        logger.debug("LLM response parsed as JSON successfully")
        return data
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM response as JSON: %s", exc)
        logger.debug("Raw response:\n%s", raw_text[:500])
        raise LLMError("Failed to parse AI response. The model returned invalid JSON.") from exc


def generate_fallback_insights(stats: dict) -> dict:
    """Generate basic insights without LLM when API unavailable.

    Uses simple heuristics and the DOMAIN_CATEGORIES mapping.

    Args:
        stats: Dictionary from analyze_browsing_data()

    Returns:
        Insights dictionary with the same structure as LLM output.
    """
    logger.info("Generating fallback (rule-based) insights")

    # Categorise domains using keyword matching
    categories: dict[str, str] = {}
    for domain_info in stats.get("domains", []):
        domain = domain_info["domain"]
        categories[domain] = _categorise_domain(domain)

    # Productivity breakdown
    productive_time = 0
    neutral_time = 0
    distracting_time = 0
    productive_cats = {"development", "productivity"}
    distracting_cats = {"social", "entertainment"}

    for domain_info in stats.get("domains", []):
        cat = categories.get(domain_info["domain"], "other")
        t = domain_info["total_time"]
        if cat in productive_cats:
            productive_time += t
        elif cat in distracting_cats:
            distracting_time += t
        else:
            neutral_time += t

    total = productive_time + neutral_time + distracting_time
    if total > 0:
        prod_pct = round(productive_time / total * 100)
        neut_pct = round(neutral_time / total * 100)
        dist_pct = 100 - prod_pct - neut_pct
    else:
        prod_pct = neut_pct = dist_pct = 0

    productivity_score = min(100, max(0, prod_pct + neut_pct // 2))

    # Determine most active period
    td = stats.get("time_distribution", {})
    periods = {
        "morning": td.get("morning", 0),
        "afternoon": td.get("afternoon", 0),
        "evening": td.get("evening", 0),
        "night": td.get("night", 0),
    }
    most_active = max(periods, key=periods.get) if any(periods.values()) else "unknown"

    # Simple summary
    top = stats.get("top_domains", [])
    top_text = ", ".join(d["domain"] for d in top[:3]) if top else "no sites"
    summary = (
        f"During this session you visited {stats.get('total_visits', 0)} pages across "
        f"{stats.get('unique_domains', 0)} unique domains. "
        f"Your most visited sites were {top_text}. "
        f"Your productivity score is {productivity_score}/100 based on domain categorisation."
    )

    return {
        "categories": categories,
        "summary": summary,
        "patterns": [
            f"Most active during the {most_active}",
            f"Top domain: {top[0]['domain']}" if top else "No dominant domain",
            f"{stats.get('unique_domains', 0)} unique sites visited",
        ],
        "productivity_score": productivity_score,
        "productivity_breakdown": {
            "productive_time": prod_pct,
            "neutral_time": neut_pct,
            "distracting_time": dist_pct,
        },
        "recommendations": [
            "Try blocking distracting sites during work hours",
            "Set specific times for checking social media",
            "Use focus mode during your most productive periods",
        ],
        "time_insights": {
            "most_active_period": most_active,
            "focus_hours": [],
            "distraction_hours": [],
        },
    }


def generate_insights(session_id: str) -> dict:
    """Generate AI insights for a browsing session.

    Queries browsing data, calls Gemini for analysis, and returns
    structured insights. Falls back to rule-based insights if the
    LLM call fails.

    Args:
        session_id: UUID of session to analyze

    Returns:
        Complete insights dictionary including stats, categories,
        summary, productivity score, recommendations, etc.

    Raises:
        ValueError: If session not found
        browserfriend.llm.InsufficientDataError: If no browsing data
    """
    from browserfriend.llm import InsufficientDataError

    # Step 1: Gather statistics
    stats = analyze_browsing_data(session_id)

    if stats["total_visits"] == 0:
        raise InsufficientDataError(f"Session {session_id} has no browsing data to analyze.")

    # Step 2: Try LLM, fall back to heuristics
    llm_insights: Optional[dict] = None
    used_fallback = False

    try:
        prompt = format_analysis_prompt(stats)
        logger.info("Calling Gemini for AI insights")
        raw_response = _call_gemini_with_retry(prompt)
        llm_insights = _parse_llm_response(raw_response)
        logger.info("AI insights generated successfully")
    except Exception as exc:
        logger.warning("LLM insight generation failed, using fallback: %s", exc)
        llm_insights = generate_fallback_insights(stats)
        used_fallback = True

    # Step 3: Assemble final result
    result = {
        "session_id": session_id,
        "stats": {
            "total_time": stats["total_time"],
            "total_visits": stats["total_visits"],
            "unique_domains": stats["unique_domains"],
            "session_duration": stats["session_duration"],
            "top_domains": stats["top_domains"],
            "time_distribution": stats["time_distribution"],
        },
        "categories": llm_insights.get("categories", {}),
        "summary": llm_insights.get("summary", ""),
        "patterns": llm_insights.get("patterns", []),
        "productivity_score": llm_insights.get("productivity_score", 0),
        "productivity_breakdown": llm_insights.get("productivity_breakdown", {}),
        "recommendations": llm_insights.get("recommendations", []),
        "time_insights": llm_insights.get("time_insights", {}),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "used_fallback": used_fallback,
    }
    logger.info(
        "Insights assembled: productivity_score=%s, fallback=%s",
        result["productivity_score"],
        used_fallback,
    )
    return result
