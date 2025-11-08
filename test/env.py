import ssl
import certifi


# Global configuration
# Sora API only supports 4, 8, or 12 seconds
LENGTH_DUR_SECONDS = 8  # Duration of generated video extension (must be 4, 8, or 12)
DEFAULT_PROMPT = "As part of a creative video production, create a scene based on this image with a comedic and entertaining style. It must be within the bounds of safe-for-work, nonviolent, and unoffensive."


# Create SSL context for secure connections
def get_ssl_context():
    """Create SSL context using certifi certificates"""
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    return ssl_context
