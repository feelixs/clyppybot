from datetime import datetime, timezone

from interactions import Extension, Task, IntervalTrigger, listen
from interactions.api.events import Startup

from ..logging_config import get_logger
from ..api_client import get_api_client
from ..services.counter_service import CounterService, CounterInfo

logger = get_logger("insightbot.tasks.counter_updater")


class CounterUpdaterTask(Extension):
    """Background task to update counter channels."""

    def __init__(self, bot):
        self.bot = bot
        self._last_updates: dict[int, datetime] = {}

    @listen(Startup)
    async def on_startup(self):
        """Start the counter update task."""
        self.update_counters.start()
        logger.info("Counter updater task started")

    @Task.create(IntervalTrigger(minutes=5))
    async def update_counters(self):
        """Update all counter channels periodically."""
        if not self.bot.is_ready:
            return

        try:
            api = get_api_client()
            counters = await api.get_all_counters()

            for record in counters:
                guild_id = record["guild_id"]
                channel_id = record["channel_id"]

                # Rate limit: max 2 updates per 10 minutes per channel
                last_update = self._last_updates.get(channel_id)
                now = datetime.now(timezone.utc)

                if last_update and (now - last_update).total_seconds() < 300:
                    continue

                # Get the guild
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue

                counter = CounterInfo(
                    id=record["id"],
                    guild_id=guild_id,
                    channel_id=channel_id,
                    counter_type=record["counter_type"],
                    template=record["template"],
                    role_id=record["role_id"],
                    goal_target=record["goal_target"],
                    last_value=record["last_value"],
                )

                # Update the counter
                new_value = await CounterService.update_counter(guild, counter)

                if new_value is not None:
                    self._last_updates[channel_id] = now
                    logger.debug(f"Updated counter {channel_id}: {counter.last_value} -> {new_value}")

        except Exception as e:
            logger.error(f"Error updating counters: {e}")

def setup(bot):
    CounterUpdaterTask(bot)
