"""Tests for the LLM integration module.

Tests data analysis, prompt formatting, fallback insights, response parsing,
and the display module. LLM API calls are mocked to avoid real API usage.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from browserfriend.database import (
    BrowsingSession,
    PageVisit,
    User,
    drop_tables,
    get_session_factory,
    init_database,
)
from browserfriend.llm import APIKeyError, InsufficientDataError, LLMError, RateLimitError
from browserfriend.llm.analyzer import (
    _parse_llm_response,
    analyze_browsing_data,
    generate_fallback_insights,
    generate_insights,
)
from browserfriend.llm.prompts import _format_seconds, format_analysis_prompt

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_database():
    """Ensure a clean database for every test."""
    drop_tables()
    init_database()
    yield
    drop_tables()


@pytest.fixture()
def sample_session():
    """Create a user and a session with page visits for testing."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        # Create user
        user = User(email="test@example.com")
        db.add(user)
        db.commit()

        # Create session
        start = datetime(2026, 2, 9, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 9, 12, 15, 0, tzinfo=timezone.utc)
        session = BrowsingSession(
            session_id="test-session-001",
            user_email="test@example.com",
            start_time=start,
            end_time=end,
            duration=(end - start).total_seconds(),
        )
        db.add(session)
        db.commit()

        # Create page visits
        visits = [
            PageVisit(
                session_id="test-session-001",
                user_email="test@example.com",
                url="https://github.com/repo",
                domain="github.com",
                title="GitHub Repo",
                start_time=start,
                end_time=start + timedelta(minutes=45),
                duration_seconds=2700,
            ),
            PageVisit(
                session_id="test-session-001",
                user_email="test@example.com",
                url="https://stackoverflow.com/q/123",
                domain="stackoverflow.com",
                title="Stack Overflow Question",
                start_time=start + timedelta(minutes=45),
                end_time=start + timedelta(minutes=75),
                duration_seconds=1800,
            ),
            PageVisit(
                session_id="test-session-001",
                user_email="test@example.com",
                url="https://youtube.com/watch?v=abc",
                domain="youtube.com",
                title="Tutorial Video",
                start_time=start + timedelta(minutes=75),
                end_time=start + timedelta(minutes=100),
                duration_seconds=1500,
            ),
            PageVisit(
                session_id="test-session-001",
                user_email="test@example.com",
                url="https://docs.python.org/3/",
                domain="docs.python.org",
                title="Python Docs",
                start_time=start + timedelta(minutes=100),
                end_time=start + timedelta(minutes=115),
                duration_seconds=900,
            ),
        ]
        db.add_all(visits)
        db.commit()

        return "test-session-001"
    finally:
        db.close()


@pytest.fixture()
def empty_session():
    """Create a session with no page visits."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        user = User(email="empty@example.com")
        db.add(user)
        db.commit()

        session = BrowsingSession(
            session_id="empty-session-001",
            user_email="empty@example.com",
            start_time=datetime(2026, 2, 9, 10, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 2, 9, 10, 5, 0, tzinfo=timezone.utc),
            duration=300,
        )
        db.add(session)
        db.commit()
        return "empty-session-001"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test: analyze_browsing_data
# ---------------------------------------------------------------------------


class TestAnalyzeBrowsingData:
    def test_returns_correct_stats(self, sample_session):
        stats = analyze_browsing_data(sample_session)

        assert stats["session_id"] == sample_session
        assert stats["total_visits"] == 4
        assert stats["unique_domains"] == 4
        assert stats["total_time"] == 2700 + 1800 + 1500 + 900  # 6900
        assert stats["session_duration"] > 0

    def test_top_domains_sorted_by_time(self, sample_session):
        stats = analyze_browsing_data(sample_session)
        top = stats["top_domains"]

        assert len(top) == 4
        assert top[0]["domain"] == "github.com"
        assert top[1]["domain"] == "stackoverflow.com"
        assert top[2]["domain"] == "youtube.com"
        assert top[3]["domain"] == "docs.python.org"

    def test_domain_percentages_sum_to_100(self, sample_session):
        stats = analyze_browsing_data(sample_session)
        total_pct = sum(d["percentage"] for d in stats["domains"])
        assert abs(total_pct - 100.0) < 0.1

    def test_time_distribution_populated(self, sample_session):
        stats = analyze_browsing_data(sample_session)
        td = stats["time_distribution"]
        # All visits start at 10am UTC = morning
        assert td["morning"] > 0

    def test_visit_timeline_chronological(self, sample_session):
        stats = analyze_browsing_data(sample_session)
        timeline = stats["visit_timeline"]
        assert len(timeline) == 4
        assert timeline[0]["domain"] == "github.com"
        assert timeline[-1]["domain"] == "docs.python.org"

    def test_session_not_found_raises(self):
        with pytest.raises(ValueError, match="Session not found"):
            analyze_browsing_data("nonexistent-session")

    def test_empty_session(self, empty_session):
        stats = analyze_browsing_data(empty_session)
        assert stats["total_visits"] == 0
        assert stats["total_time"] == 0
        assert stats["unique_domains"] == 0


# ---------------------------------------------------------------------------
# Test: format_analysis_prompt
# ---------------------------------------------------------------------------


class TestFormatAnalysisPrompt:
    def test_prompt_contains_stats(self, sample_session):
        stats = analyze_browsing_data(sample_session)
        prompt = format_analysis_prompt(stats)

        assert "4" in prompt  # total visits
        assert "github.com" in prompt
        assert "stackoverflow.com" in prompt

    def test_prompt_is_string(self, sample_session):
        stats = analyze_browsing_data(sample_session)
        prompt = format_analysis_prompt(stats)
        assert isinstance(prompt, str)
        assert len(prompt) > 100


# ---------------------------------------------------------------------------
# Test: _format_seconds
# ---------------------------------------------------------------------------


class TestFormatSeconds:
    def test_seconds(self):
        assert _format_seconds(30) == "30s"

    def test_minutes(self):
        assert _format_seconds(120) == "2m"

    def test_minutes_and_seconds(self):
        assert _format_seconds(90) == "1m 30s"

    def test_hours(self):
        assert _format_seconds(3600) == "1h"

    def test_hours_and_minutes(self):
        assert _format_seconds(5400) == "1h 30m"


# ---------------------------------------------------------------------------
# Test: _parse_llm_response
# ---------------------------------------------------------------------------


class TestParseLLMResponse:
    def test_valid_json(self):
        data = {"categories": {"github.com": "development"}, "summary": "test"}
        result = _parse_llm_response(json.dumps(data))
        assert result == data

    def test_json_with_code_fences(self):
        raw = '```json\n{"summary": "hello"}\n```'
        result = _parse_llm_response(raw)
        assert result["summary"] == "hello"

    def test_json_with_plain_fences(self):
        raw = '```\n{"summary": "world"}\n```'
        result = _parse_llm_response(raw)
        assert result["summary"] == "world"

    def test_invalid_json_raises(self):
        with pytest.raises(LLMError, match="invalid JSON"):
            _parse_llm_response("this is not json")


# ---------------------------------------------------------------------------
# Test: generate_fallback_insights
# ---------------------------------------------------------------------------


class TestGenerateFallbackInsights:
    def test_basic_structure(self, sample_session):
        stats = analyze_browsing_data(sample_session)
        insights = generate_fallback_insights(stats)

        assert "categories" in insights
        assert "summary" in insights
        assert "patterns" in insights
        assert "productivity_score" in insights
        assert "productivity_breakdown" in insights
        assert "recommendations" in insights
        assert "time_insights" in insights

    def test_domains_categorised(self, sample_session):
        stats = analyze_browsing_data(sample_session)
        insights = generate_fallback_insights(stats)

        assert insights["categories"]["github.com"] == "development"
        assert insights["categories"]["stackoverflow.com"] == "development"
        assert insights["categories"]["youtube.com"] == "entertainment"

    def test_productivity_score_range(self, sample_session):
        stats = analyze_browsing_data(sample_session)
        insights = generate_fallback_insights(stats)

        assert 0 <= insights["productivity_score"] <= 100

    def test_breakdown_sums_to_100(self, sample_session):
        stats = analyze_browsing_data(sample_session)
        insights = generate_fallback_insights(stats)

        bd = insights["productivity_breakdown"]
        total = bd["productive_time"] + bd["neutral_time"] + bd["distracting_time"]
        assert total == 100


# ---------------------------------------------------------------------------
# Test: generate_insights (with mocked LLM)
# ---------------------------------------------------------------------------


class TestGenerateInsights:
    def test_with_mocked_gemini(self, sample_session):
        """Test full pipeline with a mocked Gemini response."""
        fake_response = {
            "categories": {
                "github.com": "development",
                "stackoverflow.com": "development",
                "youtube.com": "entertainment",
                "docs.python.org": "development",
            },
            "summary": "Great coding session with strong focus.",
            "patterns": ["Deep focus on development", "Short entertainment breaks"],
            "productivity_score": 85,
            "productivity_breakdown": {
                "productive_time": 78,
                "neutral_time": 7,
                "distracting_time": 15,
            },
            "recommendations": ["Keep up the focused work!"],
            "time_insights": {
                "most_active_period": "morning",
                "focus_hours": ["10am-11am"],
                "distraction_hours": [],
            },
        }

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(fake_response)
        mock_model.generate_content.return_value = mock_response

        with patch("browserfriend.llm.analyzer._get_gemini_model", return_value=mock_model):
            insights = generate_insights(sample_session)

        assert insights["session_id"] == sample_session
        assert insights["productivity_score"] == 85
        assert insights["summary"] == "Great coding session with strong focus."
        assert insights["used_fallback"] is False
        assert "stats" in insights
        assert insights["stats"]["total_visits"] == 4

    def test_falls_back_on_llm_failure(self, sample_session):
        """When the LLM fails the system should use fallback insights."""
        with patch(
            "browserfriend.llm.analyzer._get_gemini_model",
            side_effect=Exception("API down"),
        ):
            insights = generate_insights(sample_session)

        assert insights["used_fallback"] is True
        assert insights["productivity_score"] >= 0
        assert insights["summary"] != ""

    def test_empty_session_raises(self, empty_session):
        with pytest.raises(InsufficientDataError):
            generate_insights(empty_session)

    def test_nonexistent_session_raises(self):
        with pytest.raises(ValueError, match="Session not found"):
            generate_insights("does-not-exist")


# ---------------------------------------------------------------------------
# Test: display_insights (smoke test – just ensure no crash)
# ---------------------------------------------------------------------------


class TestDisplayInsights:
    def test_display_does_not_crash(self, sample_session):
        """display_insights should run without error on valid data."""
        from browserfriend.llm.display import display_insights

        stats = analyze_browsing_data(sample_session)
        insights = generate_fallback_insights(stats)
        insights["stats"] = {
            "total_time": stats["total_time"],
            "total_visits": stats["total_visits"],
            "unique_domains": stats["unique_domains"],
            "session_duration": stats["session_duration"],
            "top_domains": stats["top_domains"],
            "time_distribution": stats["time_distribution"],
        }
        insights["session_id"] = sample_session
        insights["generated_at"] = datetime.now(timezone.utc).isoformat()
        insights["used_fallback"] = True

        # Should not raise
        display_insights(insights)


# ---------------------------------------------------------------------------
# Test: Error classes
# ---------------------------------------------------------------------------


class TestErrorClasses:
    def test_llm_error_hierarchy(self):
        assert issubclass(APIKeyError, LLMError)
        assert issubclass(RateLimitError, LLMError)
        assert issubclass(InsufficientDataError, LLMError)

    def test_error_messages(self):
        e = APIKeyError("missing key")
        assert str(e) == "missing key"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
