"""Configuration management for BrowserFriend."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Application configuration."""

    # Server settings
    server_host: str = "127.0.0.1"
    server_port: int = 8000

    # Database settings
    database_path: Optional[str] = None

    # LLM settings
    llm_provider: str = "google"  # "google" or "openai"
    google_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None  # Alias for google_api_key
    openai_api_key: Optional[str] = None

    # Email settings
    email_provider: str = "smtp"  # "smtp" or "resend"
    resend_api_key: Optional[str] = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    user_email: Optional[str] = None

    # Session settings
    session_timeout_minutes: int = 30  # Minutes of inactivity before session is considered stale

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set default database path if not provided
        if self.database_path is None:
            config_dir = Path.home() / ".browserfriend"
            config_dir.mkdir(exist_ok=True)
            self.database_path = str(config_dir / "browserfriend.db")

    def get_config_status(self) -> dict:
        """Get configuration status report."""
        status = {
            "configured": [],
            "missing": [],
            "optional": [],
        }

        # Required settings
        if self.google_api_key and self.google_api_key != "your_google_api_key_here":
            status["configured"].append("Google API Key")
        else:
            status["missing"].append("Google API Key")

        if self.openai_api_key and self.openai_api_key != "your_openai_api_key_here":
            status["configured"].append("OpenAI API Key")
        else:
            status["optional"].append("OpenAI API Key (optional if using Google)")

        if self.resend_api_key and self.resend_api_key != "your_resend_api_key_here":
            status["configured"].append("Resend API Key")
        else:
            status["missing"].append("Resend API Key")

        if self.user_email and self.user_email != "your_email@example.com":
            status["configured"].append("User Email")
        else:
            status["missing"].append("User Email")

        # Optional settings (with defaults)
        status["optional"].append(f"Server Host (default: {self.server_host})")
        status["optional"].append(f"Server Port (default: {self.server_port})")
        status["optional"].append(f"Database Path (default: {self.database_path})")
        status["optional"].append(f"LLM Provider (default: {self.llm_provider})")
        status["optional"].append(f"Log Level (default: {self.log_level})")

        return status


def get_config() -> Config:
    """Get application configuration."""
    config = Config()

    # HACKATHON DEMO: Fallback to demo keys when env not configured.
    # REMOVE this block before next release!
    try:
        from browserfriend import demo_keys

        if not config.google_api_key or config.google_api_key == "your_google_api_key_here":
            config.google_api_key = getattr(demo_keys, "GEMINI_API_KEY", None)
        if not config.resend_api_key or config.resend_api_key == "your_resend_api_key_here":
            config.resend_api_key = getattr(demo_keys, "RESEND_API_KEY", None)
        if not config.smtp_username or config.smtp_username == "your_email@example.com":
            config.smtp_username = getattr(demo_keys, "SMTP_USERNAME", None)
        if not config.smtp_password:
            config.smtp_password = getattr(demo_keys, "SMTP_PASSWORD", None)
        if getattr(demo_keys, "EMAIL_PROVIDER", None):
            config.email_provider = demo_keys.EMAIL_PROVIDER
    except Exception:
        pass

    return config
