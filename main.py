"""Main entry point for BrowserFriend FastAPI server."""

import uvicorn

from browserfriend.config import get_config

config = get_config()


def main():
    """Main entry point."""
    uvicorn.run(
        "browserfriend.server.app:app",
        host=config.server_host,
        port=config.server_port,
        reload=False,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
