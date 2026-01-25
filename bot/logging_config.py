"""Centralized logging configuration for the bot."""
import logging
from .config import config


def setup_logging() -> None:
    """Configure logging with the global log level from config."""
    log_level = getattr(logging, config.log_level, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name.

    Args:
        name: Logger name (typically __name__ or module path like "insightbot.events.members")

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
