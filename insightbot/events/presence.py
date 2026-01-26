from datetime import datetime, timezone

from interactions import Extension, listen, ActivityType
from interactions.api.events import PresenceUpdate

from ..logging_config import get_logger
from ..api_client import get_api_client
from ..services.event_queue import get_event_queue, EVENT_USER_LAST_ONLINE

logger = get_logger("insightbot.events.presence")


class PresenceEvents(Extension):
    """Handle presence update events for game tracking."""

    @listen(PresenceUpdate)
    async def on_presence_update(self, event: PresenceUpdate):
        """Track game session statistics."""
        # Ignore if no guild
        if not event.guild_id:
            return

        # Ignore bots
        if event.user and event.user.bot:
            return

        guild_id = int(event.guild_id)
        if not event.user:
            logger.info(f"No user in event {event}")
            return

        try:
            now = datetime.now(timezone.utc)
            api = get_api_client()

            # Find game activity in current state
            current_game = None
            if event.activities:
                for activity in event.activities:
                    if activity.type == ActivityType.GAME:
                        current_game = {
                            "name": activity.name,
                            "application_id": int(activity.application_id) if activity.application_id else None,
                        }
                        break

            if current_game:
                # Upsert user to discord_users
                if event.user:
                    await api.upsert_discord_user(
                        user=event.user,
                        global_name=getattr(event.user, 'global_name', None),
                    )

                # User is playing a game - start/update session
                await api.start_game_session(
                    guild_id=guild_id,
                    user_id=event.user.id,
                    game_name=current_game["name"],
                    started_at=now,
                    application_id=current_game.get("application_id"),
                )
                logger.debug(
                    f"Game session active for user {event.user.id} in guild {guild_id}: {current_game['name']}"
                )
            else:
                # User is not playing - end any active session
                result = await api.end_game_session(
                    guild_id=guild_id,
                    user_id=event.user.id,
                    ended_at=now,
                )
                if result and result.get("duration_seconds"):
                    logger.debug(
                        f"Ended game session for user {event.user.id} in guild {guild_id} "
                        f"(duration: {result.get('duration_seconds')}s)"
                    )

            # Track online status
            if event.status and event.status in ['online', 'idle', 'dnd']:
                # User is online - enqueue last_online update
                queue = get_event_queue()
                await queue.enqueue(EVENT_USER_LAST_ONLINE, {
                    "user_id": int(event.user.id),
                })

        except Exception as e:
            logger.error(f"Error tracking presence state: {e}")


def setup(bot):
    PresenceEvents(bot)
