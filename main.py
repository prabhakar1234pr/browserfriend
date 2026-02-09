"""Main entry point for BrowserFriend FastAPI server."""
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from browserfriend.config import get_config

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

    yield

    # Shutdown
    logger.info("BrowserFriend server shutting down")


# Initialize FastAPI app with lifespan
app = FastAPI(title="BrowserFriend", version="0.1.0", lifespan=lifespan)


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


def main():
    """Main entry point."""
    logger.info("Starting BrowserFriend server")
    uvicorn.run(
        "main:app",
        host=config.server_host,
        port=config.server_port,
        reload=False,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
