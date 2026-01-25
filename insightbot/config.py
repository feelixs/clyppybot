import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Bot configuration loaded from environment variables."""

    # Discord
    discord_token: str
    discord_client_id: str
    discord_client_secret: str

    # Web API
    api_base_url: str
    bot_api_key: str

    # OpenAI (for AI insights)
    openai_api_key: str

    # Logging
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            discord_token=os.environ["DISCORD_TOKEN"],
            discord_client_id=os.environ.get("DISCORD_CLIENT_ID"),
            discord_client_secret=os.environ.get("DISCORD_CLIENT_SECRET"),
            api_base_url=os.getenv("API_BASE_URL", "http://localhost:8000"),
            bot_api_key=os.environ["BOT_API_KEY"],
            openai_api_key=os.getenv("MY_OPENAI_API_KEY", ""),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


config = Config.from_env()
