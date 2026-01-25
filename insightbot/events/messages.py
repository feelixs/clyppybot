from datetime import datetime, timezone

from interactions import Extension, listen
from interactions.api.events import MessageCreate

from ..logging_config import get_logger
from ..api_client import get_api_client

logger = get_logger("insightbot.events.messages")


class MessageEvents(Extension):
    """Handle message-related events."""

    @listen(MessageCreate)
    async def on_message_create(self, event: MessageCreate):
        """Track message statistics."""
        message = event.message

        # Ignore DMs and bot messages
        if not message.guild or message.author.bot:
            return

        try:
            # Get the hour bucket (truncate to hour)
            now = datetime.now(timezone.utc)
            hour_bucket = now.replace(minute=0, second=0, microsecond=0)

            api = get_api_client()

            # Upsert user to discord_users (ensures we have their profile)
            await api.upsert_discord_user(
                user=message.author,
                global_name=getattr(message.author, 'global_name', None),
            )

            # Increment message count
            await api.increment_message_count(
                guild_id=int(message.guild.id),
                channel_id=int(message.channel.id),
                user_id=int(message.author.id),
                hour_bucket=hour_bucket,
                message_count=1,
                character_count=len(message.content) if message.content else 0,
            )
        except Exception as e:
            logger.error(f"Error tracking message: {e}")


def setup(bot):
    MessageEvents(bot)
