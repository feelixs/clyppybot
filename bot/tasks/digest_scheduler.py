from datetime import datetime, timezone

from interactions import Extension, Task, IntervalTrigger, listen
from interactions.api.events import Startup

from ..logging_config import get_logger
from ..api_client import get_api_client
from ..services.digest_service import DigestService

logger = get_logger("insightbot.tasks.digest_scheduler")


class DigestSchedulerTask(Extension):
    """Background task to send scheduled digests."""

    def __init__(self, bot):
        self.bot = bot

    @listen(Startup)
    async def on_startup(self):
        """Start the digest scheduler task."""
        self.check_digests.start()
        logger.info("Digest scheduler task started")

    @Task.create(IntervalTrigger(minutes=30))
    async def check_digests(self):
        """Check for and send due digests."""
        if not self.bot.is_ready:
            return

        try:
            now = datetime.now(timezone.utc)
            current_day = now.weekday()
            current_hour = now.hour

            api = get_api_client()
            due_digests = await api.get_due_digests(current_day, current_hour)

            for config in due_digests:
                guild_id = config["guild_id"]
                channel_id = config["channel_id"]

                # Check if already sent this week
                last_sent = config.get("last_sent_at")
                if last_sent:
                    if isinstance(last_sent, str):
                        last_sent = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
                    days_since = (now - last_sent).days
                    if days_since < 6:
                        continue

                # Get the guild
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    logger.warning(f"Guild {guild_id} not found for digest")
                    continue

                # Get the channel
                channel = await guild.fetch_channel(channel_id)
                if not channel:
                    logger.warning(f"Channel {channel_id} not found for digest in guild {guild_id}")
                    continue

                try:
                    # Generate and send digest
                    data = await DigestService.get_digest_data(guild)
                    embed = DigestService.create_digest_embed(data)

                    await channel.send(embed=embed)

                    # Mark as sent
                    await api.mark_digest_sent(guild_id)

                    logger.info(f"Sent weekly digest to guild {guild_id}")

                except Exception as e:
                    logger.error(f"Error sending digest to guild {guild_id}: {e}")

        except Exception as e:
            logger.error(f"Error checking digests: {e}")

def setup(bot):
    DigestSchedulerTask(bot)
