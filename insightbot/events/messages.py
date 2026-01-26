from datetime import datetime, timezone

from interactions import Extension, listen
from interactions.api.events import MessageCreate

from ..logging_config import get_logger
from ..services.event_queue import get_event_queue, EVENT_USER_UPSERT, EVENT_MESSAGE

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

            queue = get_event_queue()

            # Enqueue user upsert (ensures we have their profile)
            await queue.enqueue(EVENT_USER_UPSERT, {
                "user_id": int(message.author.id),
                "username": message.author.username,
                "global_name": getattr(message.author, 'global_name', None),
                "avatar_hash": message.author.avatar.hash if message.author.avatar else None,
            })

            # Enqueue message increment
            await queue.enqueue(EVENT_MESSAGE, {
                "guild_id": int(message.guild.id),
                "channel_id": int(message.channel.id),
                "user_id": int(message.author.id),
                "hour_bucket": hour_bucket.isoformat(),
                "message_count": 1,
                "character_count": len(message.content) if message.content else 0,
            })
        except Exception as e:
            logger.error(f"Error queueing message event: {e}")


def setup(bot):
    MessageEvents(bot)
