"""Background task to process batched events from the SQLite queue."""

from interactions import Extension, Task, IntervalTrigger, listen
from interactions.api.events import Startup

from ..logging_config import get_logger
from ..api_client import get_api_client
from ..services.event_queue import (
    get_event_queue,
    EVENT_USER_UPSERT,
    EVENT_MESSAGE,
    EVENT_VOICE_START,
    EVENT_VOICE_END,
    EVENT_USER_LAST_ONLINE,
)
from .. import intent_flags

logger = get_logger("insightbot.tasks.event_queue_processor")


class EventQueueProcessor(Extension):
    """Background task that drains the event queue every 20 seconds."""

    def __init__(self, bot):
        self.bot = bot

    @listen(Startup)
    async def on_startup(self):
        """Start the event queue processor task."""
        self.process_queue.start()
        logger.info("Event queue processor task started (5s interval)")

    @Task.create(IntervalTrigger(seconds=5))
    async def process_queue(self):
        """Process all pending events in batches until queue is empty."""
        if not self.bot.is_ready:
            return

        queue = get_event_queue()
        api = get_api_client()

        # Process each event type
        # IMPORTANT: VOICE_END must come before VOICE_START so that channel switches
        # (which queue an end + start) close the old session before opening the new one.
        event_types = [EVENT_USER_UPSERT, EVENT_MESSAGE, EVENT_VOICE_END, EVENT_VOICE_START]

        # Only process EVENT_USER_LAST_ONLINE if GUILD_PRESENCES intent is available
        if intent_flags.HAS_GUILD_PRESENCES:
            event_types.append(EVENT_USER_LAST_ONLINE)

        for event_type in event_types:
            # Drain-until-empty pattern
            while True:
                try:
                    events = await queue.fetch_batch(event_type, limit=100)

                    if not events:
                        break  # Queue is empty for this type

                    # Process the batch
                    event_ids = [e["id"] for e in events]

                    try:
                        if event_type == EVENT_USER_UPSERT:
                            await self._process_user_upserts(api, events)
                        elif event_type == EVENT_MESSAGE:
                            await self._process_messages(api, events)
                        elif event_type == EVENT_VOICE_START:
                            await self._process_voice_starts(api, events)
                        elif event_type == EVENT_VOICE_END:
                            await self._process_voice_ends(api, events)
                        elif event_type == EVENT_USER_LAST_ONLINE:
                            await self._process_user_last_online(api, events)

                        # Mark as processed (delete from queue)
                        await queue.mark_processed(event_ids)
                        logger.info(f"Processed {len(events)} {event_type} events")

                    except Exception as e:
                        # Mark as failed and break to avoid hammering failing API
                        await queue.mark_failed(event_ids, str(e))
                        logger.error(f"Failed to process {event_type} batch: {e}")
                        break  # Stop processing this type to avoid continuous failures

                except Exception as e:
                    logger.error(f"Error fetching {event_type} batch: {e}")
                    break

        # Log queue depth if not empty
        depths = await queue.get_queue_depth()
        if depths:
            logger.info(f"Queue depths: {depths}")

    async def _process_user_upserts(self, api, events):
        """Process user_upsert events."""
        users = [e["payload"] for e in events]
        count = await api.bulk_upsert_discord_users(users)
        logger.debug(f"Upserted {count} Discord users")

    async def _process_messages(self, api, events):
        """Process message events."""
        messages = [e["payload"] for e in events]
        await api.batch_increment_message_counts(messages)
        logger.debug(f"Incremented {len(messages)} message counts")

    async def _process_voice_starts(self, api, events):
        """Process voice_start events."""
        sessions = [e["payload"] for e in events]
        await api.batch_start_voice_sessions(sessions)
        logger.debug(f"Started {len(sessions)} voice sessions")

    async def _process_voice_ends(self, api, events):
        """Process voice_end events."""
        sessions = [e["payload"] for e in events]
        await api.batch_end_voice_sessions(sessions)
        logger.debug(f"Ended {len(sessions)} voice sessions")

    async def _process_user_last_online(self, api, events):
        """Process user_last_online events."""
        user_ids = [e["payload"]["user_id"] for e in events]
        # Deduplicate user_ids in batch
        unique_user_ids = list(set(user_ids))
        await api.batch_update_user_last_online(unique_user_ids)
        logger.debug(f"Updated last_online for {len(unique_user_ids)} users")


def setup(bot):
    EventQueueProcessor(bot)
