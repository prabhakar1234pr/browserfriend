"""FastAPI application for BrowserFriend server."""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

from browserfriend.config import get_config
from browserfriend.database import (
    PageVisit,
    User,
    create_new_session,
    extract_domain,
    get_current_session,
    get_engine,
    get_session_factory,
    init_database,
)


# Configure logging
def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """Set up logging configuration."""
    # Create logs directory if log file is specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure logging format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Configure handlers
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    # Set up logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
    )


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


class SetupData(BaseModel):
    """Model for setup endpoint email validation."""

    email: EmailStr


class SuccessResponse(BaseModel):
    """Model for success responses."""

    success: bool
    message: str


class StatusResponse(BaseModel):
    """Model for status endpoint response."""

    status: str
    database: str


class SetupResponse(BaseModel):
    """Model for setup endpoint response."""

    success: bool
    email: str


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


@app.get("/health")
async def health():
    """Health check endpoint."""
    logger.debug("Health check endpoint called")
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "BrowserFriend",
            "version": "0.1.0",
        },
    )


@app.get("/api/status", response_model=StatusResponse)
async def status():
    """Get server and database status."""
    logger.debug("Status endpoint called")
    try:
        # Check database connection
        from sqlalchemy import text

        engine = get_engine()
        with engine.connect() as conn:
            # Try a simple query to verify connection
            conn.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        db_status = f"error: {str(e)}"

    return StatusResponse(status="running", database=db_status)


@app.post("/api/setup", response_model=SetupResponse)
async def setup(setup_data: SetupData):
    """Save user email during setup.

    Validates email format and creates user record if it doesn't exist.
    """
    logger.debug(f"Setup endpoint called with email: {setup_data.email}")
    try:
        SessionLocal = get_session_factory()
        session = SessionLocal()
        try:
            # Query User table
            user = session.query(User).filter(User.email == setup_data.email).first()

            # If user doesn't exist, create new User record
            if not user:
                user = User(email=setup_data.email)
                session.add(user)
                session.commit()
                session.refresh(user)
                logger.info(f"Created new user: {user.email}")
            else:
                logger.debug(f"User already exists: {user.email}")

            return SetupResponse(success=True, email=user.email)
        except Exception as e:
            session.rollback()
            logger.error(f"Database error in setup endpoint: {e}")
            raise
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error in setup endpoint: {e}")
        raise


@app.post("/api/track", response_model=SuccessResponse)
async def track(tracking_data: TrackingData):
    """Receive completed page visit from Chrome extension.

    Creates a page visit record with session management.
    """
    logger.debug(
        f"Track endpoint called: url={tracking_data.url}, duration={tracking_data.duration}s"
    )
    try:
        SessionLocal = get_session_factory()
        session = SessionLocal()
        try:
            # 1. Validate request body with TrackingData Pydantic model (already done)

            # 2. Parse ISO timestamp string to datetime
            try:
                end_time = datetime.fromisoformat(tracking_data.timestamp.replace("Z", "+00:00"))
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=timezone.utc)
            except ValueError as e:
                logger.error(f"Invalid timestamp format: {tracking_data.timestamp}")
                raise HTTPException(
                    status_code=400, detail=f"Invalid timestamp format: {tracking_data.timestamp}"
                )

            # 3. Get user email from User table
            user = session.query(User).first()
            if not user:
                logger.error("No user found in database")
                raise HTTPException(
                    status_code=404, detail="No user found. Please run setup first."
                )
            user_email = user.email

            # 4. Get current active session or create new one
            current_session = get_current_session(user_email)
            if not current_session:
                logger.info(f"No active session found, creating new session for {user_email}")
                current_session = create_new_session(user_email)
            else:
                logger.debug(f"Using existing session: {current_session.session_id}")

            # 5. Extract domain from URL
            domain = extract_domain(tracking_data.url)

            # 6. Calculate start_time: start_time = timestamp - duration
            start_time = end_time - timedelta(seconds=tracking_data.duration)

            # 7. Create PageVisit record
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
            session.add(page_visit)
            session.commit()
            session.refresh(page_visit)

            logger.info(
                f"Created page visit: {domain} for session {current_session.session_id} "
                f"(duration: {tracking_data.duration}s)"
            )

            return SuccessResponse(
                success=True, message=f"Page visit tracked: {domain}"
            )
        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Database error in track endpoint: {e}")
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in track endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
