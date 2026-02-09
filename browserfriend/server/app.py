"""FastAPI application for BrowserFriend server."""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from browserfriend.config import get_config
from browserfriend.database import (
    BrowsingSession,
    PageVisit,
    User,
    extract_domain,
    get_engine,
    get_or_create_active_session,
    get_session_factory,
    init_database,
)


# Configure logging
def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """Set up logging configuration with maximum verbosity."""
    # Create logs directory if log file is specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure detailed logging format with more information
    log_format = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Configure handlers
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    # Set up logging with maximum verbosity
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True,  # Override any existing configuration
    )

    # Set specific loggers to DEBUG for maximum verbosity
    logging.getLogger("browserfriend").setLevel(logging.DEBUG)
    logging.getLogger("browserfriend.server").setLevel(logging.DEBUG)
    logging.getLogger("browserfriend.database").setLevel(logging.DEBUG)


# Get configuration
config = get_config()

# Set up logging
setup_logging(config.log_level, config.log_file)
logger = logging.getLogger(__name__)


# Pydantic models for request/response validation
class TrackingData(BaseModel):
    """Model for tracking page visit data."""

    url: str
    title: Optional[str] = None
    duration: int  # seconds spent on page
    timestamp: str  # ISO format timestamp when user LEFT the page (end time)
    email: EmailStr  # user email to identify which user this visit belongs to


class SetupData(BaseModel):
    """Model for setup endpoint email validation."""

    email: EmailStr


class SuccessResponse(BaseModel):
    """Model for success responses."""

    success: bool
    message: str


class TrackResponse(BaseModel):
    """Model for track endpoint response."""

    success: bool
    message: str
    session_id: str


class StatusResponse(BaseModel):
    """Model for status endpoint response."""

    status: str
    database: str


class SetupResponse(BaseModel):
    """Model for setup endpoint response."""

    success: bool
    email: str


class EndSessionRequest(BaseModel):
    """Model for session end request."""

    session_id: str


class EndSessionResponse(BaseModel):
    """Model for session end response."""

    success: bool
    message: str
    session_id: str
    duration_seconds: Optional[float] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("=" * 60)
    logger.info("BrowserFriend server starting up")
    logger.info("=" * 60)

    # Log configuration status
    config_status = config.get_config_status()
    logger.info("Configuration Status:")
    logger.info("-" * 60)

    if config_status["configured"]:
        logger.info("✓ Configured Settings:")
        for setting in config_status["configured"]:
            logger.info(f"  • {setting}")

    if config_status["missing"]:
        logger.warning("✗ Missing Required Settings:")
        for setting in config_status["missing"]:
            logger.warning(f"  • {setting}")

    if config_status["optional"]:
        logger.info("○ Optional Settings (using defaults):")
        for setting in config_status["optional"]:
            logger.info(f"  • {setting}")

    logger.info("-" * 60)

    # Check if critical settings are missing
    if config_status["missing"]:
        logger.warning(
            f"Warning: {len(config_status['missing'])} required setting(s) not configured. "
            "Some features may not work properly."
        )
    else:
        logger.info("All required settings are configured!")

    logger.info(f"Server will run on {config.server_host}:{config.server_port}")
    logger.info(f"Database: {config.database_path}")
    logger.info("=" * 60)

    # Initialize database on startup
    try:
        init_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    yield

    # Shutdown
    logger.info("BrowserFriend server shutting down")


# Initialize FastAPI app with lifespan
app = FastAPI(title="BrowserFriend", version="0.1.0", lifespan=lifespan)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"(chrome-extension://.*|http://localhost:.*)",  # Chrome extensions and localhost
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)


@app.get("/api/status", response_model=StatusResponse)
async def status():
    """Get server and database status.

    Single status/health endpoint that checks server state and database connectivity.
    """
    logger.info("Status endpoint called - checking server and database status")
    try:
        # Check database connection
        from sqlalchemy import text

        logger.debug("Getting database engine")
        engine = get_engine()
        logger.debug(f"Database engine obtained: {engine.url}")

        logger.debug("Testing database connection")
        with engine.connect() as conn:
            # Try a simple query to verify connection
            result = conn.execute(text("SELECT 1"))
            logger.debug(f"Database query executed successfully: {result.fetchone()}")
            db_status = "connected"
            logger.info("Database connection check: SUCCESS")
    except Exception as e:
        logger.error(f"Database connection check failed: {e}", exc_info=True)
        db_status = f"error: {str(e)}"
        logger.warning(f"Database status: {db_status}")

    response = StatusResponse(status="running", database=db_status)
    logger.debug(f"Status response: {response.model_dump()}")
    return response


@app.post("/api/setup", response_model=SetupResponse)
async def setup(setup_data: SetupData):
    """Save user email during setup.

    Validates email format and creates user record if it doesn't exist.
    """
    logger.info(f"Setup endpoint called with email: {setup_data.email}")
    logger.debug(f"Setup request data: {setup_data.model_dump()}")

    try:
        logger.debug("Getting session factory")
        SessionLocal = get_session_factory()
        session = SessionLocal()
        logger.debug("Database session created")

        try:
            # Query User table by email
            logger.debug(f"Querying User table for email: {setup_data.email}")
            user = session.query(User).filter(User.email == setup_data.email).first()

            if user:
                logger.info(
                    f"User already exists: id={user.id}, email={user.email} "
                    f"(created at: {user.created_at})"
                )
            else:
                logger.info(f"User not found, creating new user: {setup_data.email}")
                user = User(email=setup_data.email)
                session.add(user)
                logger.debug(f"User object added to session: {user.email}")
                session.commit()
                logger.debug("User commit successful")
                session.refresh(user)
                logger.info(
                    f"Created new user: id={user.id}, email={user.email} "
                    f"(created at: {user.created_at})"
                )

            response = SetupResponse(success=True, email=user.email)
            logger.debug(f"Setup response: {response.model_dump()}")
            logger.info(f"Setup endpoint completed successfully for: {user.email}")
            return response
        except Exception as e:
            session.rollback()
            logger.error(f"Database error in setup endpoint: {e}", exc_info=True)
            logger.error("Rolled back transaction due to error")
            raise HTTPException(status_code=500, detail=f"Database error during setup: {str(e)}")
        finally:
            session.close()
            logger.debug("Database session closed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in setup endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/api/track", response_model=TrackResponse)
async def track(tracking_data: TrackingData):
    """Receive completed page visit from Chrome extension.

    Creates a page visit record with session management.
    Requires email to identify the user (no single-user assumption).
    Returns the session_id used for this visit.
    Stale sessions (>30 min inactivity) are auto-ended and a new session is created.
    """
    logger.info(
        f"Track endpoint called: email={tracking_data.email}, url={tracking_data.url}, "
        f"title={tracking_data.title}, duration={tracking_data.duration}s, "
        f"timestamp={tracking_data.timestamp}"
    )
    logger.debug(f"Track request data: {tracking_data.model_dump()}")

    try:
        logger.debug("Getting session factory")
        SessionLocal = get_session_factory()
        session = SessionLocal()
        logger.debug("Database session created")

        try:
            # 1. Validate request body with TrackingData Pydantic model (already done)
            logger.debug("Request body validated by Pydantic")

            # 2. Parse ISO timestamp string to datetime
            logger.debug(f"Parsing timestamp: {tracking_data.timestamp}")
            try:
                timestamp_str = tracking_data.timestamp.replace("Z", "+00:00")
                logger.debug(f"Normalized timestamp string: {timestamp_str}")
                end_time = datetime.fromisoformat(timestamp_str)
                logger.debug(f"Parsed end_time: {end_time} (tzinfo: {end_time.tzinfo})")

                if end_time.tzinfo is None:
                    logger.debug("End time is timezone-naive, adding UTC timezone")
                    end_time = end_time.replace(tzinfo=timezone.utc)
                    logger.debug(f"End time with timezone: {end_time}")

                logger.info(f"Successfully parsed timestamp: {end_time}")
            except ValueError as e:
                logger.error(
                    f"Invalid timestamp format: {tracking_data.timestamp}, error: {e}",
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid timestamp format: {tracking_data.timestamp}. Expected ISO format.",
                )

            # 3. Validate user exists by email from request
            user_email = tracking_data.email
            logger.debug(f"Querying User table for email: {user_email}")
            user = session.query(User).filter(User.email == user_email).first()
            if not user:
                logger.error(f"No user found with email: {user_email} - setup required")
                raise HTTPException(
                    status_code=404,
                    detail=f"No user found with email: {user_email}. Please run setup first.",
                )
            logger.info(f"Found user: id={user.id}, email={user.email}")

            # 4. Get active session (auto-ends stale sessions, creates new if needed)
            logger.debug(f"Getting or creating active session for user: {user_email}")
            current_session = get_or_create_active_session(user_email)
            logger.info(
                f"Active session: {current_session.session_id} "
                f"(start_time: {current_session.start_time})"
            )

            # 5. Extract domain from URL
            logger.debug(f"Extracting domain from URL: {tracking_data.url}")
            domain = extract_domain(tracking_data.url)
            logger.debug(f"Extracted domain: {domain}")

            # 6. Calculate start_time: start_time = timestamp - duration
            logger.debug(
                f"Calculating start_time: end_time={end_time}, duration={tracking_data.duration}s"
            )
            start_time = end_time - timedelta(seconds=tracking_data.duration)
            logger.info(
                f"Time calculation: start_time={start_time}, end_time={end_time}, "
                f"duration={tracking_data.duration}s"
            )

            # 7. Create PageVisit record
            logger.debug("Creating PageVisit record")
            page_visit = PageVisit(
                session_id=current_session.session_id,
                user_email=user_email,
                url=tracking_data.url,
                domain=domain,
                title=tracking_data.title,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=tracking_data.duration,
            )
            logger.debug(
                f"PageVisit object created: url={page_visit.url}, domain={page_visit.domain}, "
                f"start_time={page_visit.start_time}, end_time={page_visit.end_time}, "
                f"duration={page_visit.duration_seconds}s"
            )

            session.add(page_visit)
            logger.debug("PageVisit added to session")
            session.commit()
            logger.debug("PageVisit commit successful")
            session.refresh(page_visit)
            logger.debug(f"PageVisit refreshed, ID: {page_visit.id}")

            logger.info(
                f"Successfully created page visit: ID={page_visit.id}, domain={domain}, "
                f"session={current_session.session_id}, duration={tracking_data.duration}s"
            )

            response = TrackResponse(
                success=True,
                message=f"Page visit tracked: {domain}",
                session_id=current_session.session_id,
            )
            logger.debug(f"Track response: {response.model_dump()}")
            return response
        except HTTPException:
            logger.warning("HTTPException raised in track endpoint, re-raising")
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Database error in track endpoint: {e}", exc_info=True)
            logger.error("Rolled back transaction due to error")
            raise HTTPException(status_code=500, detail=f"Database error during tracking: {str(e)}")
        finally:
            session.close()
            logger.debug("Database session closed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in track endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/api/session/end", response_model=EndSessionResponse)
async def end_session_endpoint(request: EndSessionRequest):
    """End a browsing session by setting end_time.

    Sets end_time to now and calculates session duration.
    """
    logger.info(f"End session endpoint called for session_id: {request.session_id}")
    logger.debug(f"End session request data: {request.model_dump()}")

    try:
        logger.debug("Getting session factory")
        SessionLocal = get_session_factory()
        session = SessionLocal()
        logger.debug("Database session created")

        try:
            # Find the session
            logger.debug(f"Querying BrowsingSession for id: {request.session_id}")
            browsing_session = (
                session.query(BrowsingSession)
                .filter(BrowsingSession.session_id == request.session_id)
                .first()
            )

            if not browsing_session:
                logger.error(f"Session not found: {request.session_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Session not found: {request.session_id}",
                )

            if browsing_session.end_time is not None:
                logger.warning(
                    f"Session {request.session_id} is already ended "
                    f"(end_time: {browsing_session.end_time})"
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"Session {request.session_id} is already ended.",
                )

            # End the session
            logger.debug(f"Ending session: {request.session_id}")
            browsing_session.end_time = datetime.now(timezone.utc)
            browsing_session.calculate_duration()
            session.commit()
            session.refresh(browsing_session)

            logger.info(
                f"Session ended: {request.session_id}, "
                f"duration={browsing_session.duration}s, "
                f"end_time={browsing_session.end_time}"
            )

            response = EndSessionResponse(
                success=True,
                message="Session ended successfully",
                session_id=request.session_id,
                duration_seconds=browsing_session.duration,
            )
            logger.debug(f"End session response: {response.model_dump()}")
            return response
        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Database error in end session endpoint: {e}", exc_info=True)
            logger.error("Rolled back transaction due to error")
            raise HTTPException(status_code=500, detail=f"Database error ending session: {str(e)}")
        finally:
            session.close()
            logger.debug("Database session closed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in end session endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
