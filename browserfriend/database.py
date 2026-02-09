"""Database models and setup for BrowserFriend."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    create_engine,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

from browserfriend.config import get_config

logger = logging.getLogger(__name__)

Base = declarative_base()


def extract_domain(url: str) -> str:
    """Extract domain from a URL.

    Args:
        url: The URL to extract domain from

    Returns:
        The domain name (e.g., 'google.com' from 'https://www.google.com/search')
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        # Remove 'www.' prefix if present
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower() if domain else "unknown"
    except Exception as e:
        logger.warning(f"Failed to extract domain from URL '{url}': {e}")
        return "unknown"


class User(Base):
    """Model representing a user."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, created_at={self.created_at})>"


class BrowsingSession(Base):
    """Model representing a browsing session."""

    __tablename__ = "browsing_sessions"

    session_id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_email = Column(String, nullable=False, index=True)
    start_time = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    end_time = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True)  # Duration in seconds

    # Relationship to page visits
    page_visits = relationship("PageVisit", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<BrowsingSession(session_id={self.session_id}, user_email={self.user_email}, start_time={self.start_time})>"

    def calculate_duration(self):
        """Calculate duration from start_time and end_time."""
        if self.end_time and self.start_time:
            end = self.end_time
            start = self.start_time
            # Normalize timezone awareness for comparison
            if end.tzinfo is not None and start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            elif end.tzinfo is None and start.tzinfo is not None:
                end = end.replace(tzinfo=timezone.utc)
            delta = end - start
            self.duration = delta.total_seconds()
        return self.duration


class PageVisit(Base):
    """Model representing a page visit within a browsing session."""

    __tablename__ = "page_visits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String, ForeignKey("browsing_sessions.session_id"), nullable=False, index=True
    )
    user_email = Column(String, nullable=False, index=True)
    url = Column(String, nullable=False)
    domain = Column(String, nullable=False, index=True)
    title = Column(String, nullable=True)
    start_time = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Relationship to browsing session
    session = relationship("BrowsingSession", back_populates="page_visits")

    def __repr__(self):
        return f"<PageVisit(id={self.id}, url={self.url}, domain={self.domain}, duration={self.duration_seconds})>"

    def calculate_duration(self):
        """Calculate duration from start_time and end_time."""
        if self.end_time and self.start_time:
            delta = self.end_time - self.start_time
            self.duration_seconds = delta.total_seconds()
        return self.duration_seconds


# Create indexes for common queries
Index("idx_page_visits_session_id", PageVisit.session_id)
Index("idx_page_visits_domain", PageVisit.domain)
Index("idx_page_visits_start_time", PageVisit.start_time)
Index("idx_page_visits_end_time", PageVisit.end_time)
Index("idx_page_visits_user_email", PageVisit.user_email)
Index("idx_browsing_sessions_user_email", BrowsingSession.user_email)
Index("idx_browsing_sessions_start_time", BrowsingSession.start_time)


# Database engine and session factory
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        config = get_config()
        database_url = f"sqlite:///{config.database_path}"

        # Ensure the directory exists
        db_path = Path(config.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        _engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},  # Needed for SQLite
            echo=False,  # Set to True for SQL query logging
        )
        logger.info(f"Database engine created: {database_url}")
    return _engine


def get_session_factory():
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info("Session factory created")
    return _SessionLocal


def get_db_session():
    """Get a database session."""
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_database():
    """Initialize the database by creating all tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")


def create_tables():
    """Create all database tables (alias for init_database)."""
    init_database()


def drop_tables():
    """Drop all database tables (use with caution!)."""
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    logger.warning("All database tables dropped")


def get_current_session(user_email: str) -> Optional[BrowsingSession]:
    """Get the current active session for a user, if any."""
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        current_session = (
            session.query(BrowsingSession)
            .filter(
                BrowsingSession.user_email == user_email,
                BrowsingSession.end_time.is_(None),
            )
            .order_by(BrowsingSession.start_time.desc())
            .first()
        )
        return current_session
    finally:
        session.close()


def get_or_create_active_session(
    user_email: str, inactivity_timeout_minutes: Optional[int] = None
) -> BrowsingSession:
    """Get active session or create a new one, closing stale sessions first.

    If an active session exists but the last page visit was more than
    `inactivity_timeout_minutes` ago, the old session is ended and a new one
    is created. This prevents sessions from staying active forever.

    Args:
        user_email: The user's email address
        inactivity_timeout_minutes: Minutes of inactivity before session is considered stale.
            Defaults to config.session_timeout_minutes (30).

    Returns:
        An active BrowsingSession
    """
    if inactivity_timeout_minutes is None:
        config = get_config()
        inactivity_timeout_minutes = config.session_timeout_minutes

    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        # Find current active session
        current = (
            session.query(BrowsingSession)
            .filter(
                BrowsingSession.user_email == user_email,
                BrowsingSession.end_time.is_(None),
            )
            .order_by(BrowsingSession.start_time.desc())
            .first()
        )

        if current:
            # Check last page visit in this session to detect staleness
            last_visit = (
                session.query(PageVisit)
                .filter(PageVisit.session_id == current.session_id)
                .order_by(PageVisit.end_time.desc())
                .first()
            )

            cutoff = datetime.now(timezone.utc) - timedelta(minutes=inactivity_timeout_minutes)

            # Determine the latest activity timestamp
            last_activity = None
            if last_visit and last_visit.end_time:
                last_activity = last_visit.end_time
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=timezone.utc)

            if last_activity and last_activity < cutoff:
                # Session is stale — end it
                logger.info(
                    f"Session {current.session_id} is stale "
                    f"(last activity: {last_activity}, cutoff: {cutoff}). Ending it."
                )
                current.end_time = datetime.now(timezone.utc)
                current.calculate_duration()
                session.commit()
                session.refresh(current)
                logger.info(f"Ended stale session: {current.session_id}")
                current = None  # Force creation of new session below
            else:
                logger.debug(
                    f"Session {current.session_id} is still active (last activity: {last_activity})"
                )
                return current

        # No active session (or stale one was just ended) — create new
        logger.info(f"Creating new session for user: {user_email}")
        new_session = BrowsingSession(
            session_id=str(uuid4()),
            user_email=user_email,
            start_time=datetime.now(timezone.utc),
        )
        session.add(new_session)
        session.commit()
        session.refresh(new_session)
        logger.info(
            f"Created new browsing session: {new_session.session_id} for user: {user_email}"
        )
        return new_session
    finally:
        session.close()


def create_new_session(user_email: str) -> BrowsingSession:
    """Create a new browsing session for a user."""
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        new_session = BrowsingSession(
            session_id=str(uuid4()),
            user_email=user_email,
            start_time=datetime.now(timezone.utc),
        )
        session.add(new_session)
        session.commit()
        session.refresh(new_session)
        logger.info(
            f"Created new browsing session: {new_session.session_id} for user: {user_email}"
        )
        return new_session
    finally:
        session.close()


def end_session(session_id: str) -> Optional[BrowsingSession]:
    """End a browsing session by setting end_time and calculating duration."""
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        browsing_session = (
            session.query(BrowsingSession).filter(BrowsingSession.session_id == session_id).first()
        )
        if browsing_session:
            browsing_session.end_time = datetime.now(timezone.utc)
            browsing_session.calculate_duration()
            session.commit()
            session.refresh(browsing_session)
            logger.info(f"Ended browsing session: {session_id}")
            return browsing_session
        return None
    finally:
        session.close()


def create_page_visit(
    session_id: str,
    user_email: str,
    url: str,
    title: Optional[str] = None,
    start_time: Optional[datetime] = None,
) -> PageVisit:
    """Create a new page visit with automatic domain extraction.

    Args:
        session_id: The browsing session ID
        user_email: The user's email address
        url: The page URL
        title: Optional page title
        start_time: Optional start time (defaults to now)

    Returns:
        The created PageVisit object
    """
    SessionLocal = get_session_factory()
    db_session = SessionLocal()
    try:
        domain = extract_domain(url)
        if start_time is None:
            start_time = datetime.now(timezone.utc)

        page_visit = PageVisit(
            session_id=session_id,
            user_email=user_email,
            url=url,
            domain=domain,
            title=title,
            start_time=start_time,
        )
        db_session.add(page_visit)
        db_session.commit()
        db_session.refresh(page_visit)
        logger.debug(f"Created page visit: {domain} for session {session_id}")
        return page_visit
    finally:
        db_session.close()


def get_sessions_by_user(user_email: str, limit: Optional[int] = None) -> List[BrowsingSession]:
    """Get all sessions for a user, ordered by start_time descending.

    Args:
        user_email: The user's email address
        limit: Optional limit on number of sessions to return

    Returns:
        List of BrowsingSession objects
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        query = (
            session.query(BrowsingSession)
            .filter(BrowsingSession.user_email == user_email)
            .order_by(BrowsingSession.start_time.desc())
        )

        if limit:
            query = query.limit(limit)

        return query.all()
    finally:
        session.close()


def get_visits_by_user(user_email: str, limit: Optional[int] = None) -> List[PageVisit]:
    """Get all page visits for a user, ordered by start_time descending.

    Args:
        user_email: The user's email address
        limit: Optional limit on number of visits to return

    Returns:
        List of PageVisit objects
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        query = (
            session.query(PageVisit)
            .filter(PageVisit.user_email == user_email)
            .order_by(PageVisit.start_time.desc())
        )

        if limit:
            query = query.limit(limit)

        return query.all()
    finally:
        session.close()


def get_visits_by_session(session_id: str) -> List[PageVisit]:
    """Get all page visits for a specific session.

    Args:
        session_id: The browsing session ID

    Returns:
        List of PageVisit objects
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        return (
            session.query(PageVisit)
            .filter(PageVisit.session_id == session_id)
            .order_by(PageVisit.start_time.asc())
            .all()
        )
    finally:
        session.close()


def get_top_domains_by_user(user_email: str, limit: int = 10) -> List[tuple]:
    """Get top visited domains for a user by visit count.

    Args:
        user_email: The user's email address
        limit: Number of top domains to return (default: 10)

    Returns:
        List of tuples (domain, count)
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        results = (
            session.query(PageVisit.domain, func.count(PageVisit.id).label("count"))
            .filter(PageVisit.user_email == user_email)
            .group_by(PageVisit.domain)
            .order_by(func.count(PageVisit.id).desc())
            .limit(limit)
            .all()
        )
        return [(domain, count) for domain, count in results]
    finally:
        session.close()


def get_total_time_by_user(user_email: str) -> float:
    """Get total browsing time (in seconds) for a user across all sessions.

    Args:
        user_email: The user's email address

    Returns:
        Total time in seconds
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        result = (
            session.query(func.sum(BrowsingSession.duration))
            .filter(
                BrowsingSession.user_email == user_email,
                BrowsingSession.duration.isnot(None),
            )
            .scalar()
        )
        return float(result) if result else 0.0
    finally:
        session.close()


def get_user_email_from_session(session_id: str) -> Optional[str]:
    """Get user email from a session ID.

    Args:
        session_id: The browsing session ID

    Returns:
        User email or None if session not found
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        browsing_session = (
            session.query(BrowsingSession).filter(BrowsingSession.session_id == session_id).first()
        )
        return browsing_session.user_email if browsing_session else None
    finally:
        session.close()
