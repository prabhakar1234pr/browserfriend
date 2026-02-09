"""FastAPI application for BrowserFriend server."""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

from browserfriend.config import get_config
from browserfriend.database import get_engine, init_database


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
