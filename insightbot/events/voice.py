from datetime import datetime, timezone

from interactions import Extension, listen
from interactions.api.events import VoiceStateUpdate

from ..logging_config import get_logger
from ..services.event_queue import (
    get_event_queue,
    EVENT_USER_UPSERT,
    EVENT_VOICE_START,
    EVENT_VOICE_END,
)

logger = get_logger("insightbot.events.voice")


class VoiceEvents(Extension):
    """Handle voice state events."""

    @listen(VoiceStateUpdate)
    async def on_voice_state_update(self, event: VoiceStateUpdate):
        """Track voice session statistics."""
        before = event.before
        after = event.after

        # Get guild from whichever state has it (after for joins, before for leaves)
        guild = None
        if after and after.guild:
            guild = after.guild
        elif before and before.guild:
            guild = before.guild

        if not guild:
            return

        guild_id = int(guild.id)

        # Get user reference from whichever state has it
        user_ref = None
        if after and after.member:
            user_ref = after.member.user
        elif before and before.member:
            user_ref = before.member.user

        if not user_ref:
            return

        try:
            now = datetime.now(timezone.utc)
            queue = get_event_queue()

            # User joined a voice channel
            if not before or not before.channel:
                if after.channel:
                    # Enqueue user upsert
                    member = after.member
                    if member:
                        await queue.enqueue(EVENT_USER_UPSERT, {
                            "user_id": int(user_ref.id),
                            "username": user_ref.username,
                            "global_name": member.global_name,
                            "avatar_hash": user_ref.avatar.hash if user_ref.avatar else None,
                        })

                    # Enqueue voice session start
                    await queue.enqueue(EVENT_VOICE_START, {
                        "guild_id": guild_id,
                        "channel_id": int(after.channel.id),
                        "user_id": int(user_ref.id),
                        "started_at": now.isoformat(),
                    })
                    logger.debug(f"Queued voice session start for user {user_ref.id} in guild {guild_id}")

            # User left a voice channel
            elif before.channel and (not after or not after.channel or after.channel.id != before.channel.id):
                # Enqueue voice session end
                await queue.enqueue(EVENT_VOICE_END, {
                    "guild_id": guild_id,
                    "user_id": int(user_ref.id),
                    "ended_at": now.isoformat(),
                })
                logger.debug(f"Queued voice session end for user {user_ref.id} in guild {guild_id}")

                # If they moved to another channel, start a new session
                if after and after.channel and (not before.channel or after.channel.id != before.channel.id):
                    await queue.enqueue(EVENT_VOICE_START, {
                        "guild_id": guild_id,
                        "channel_id": int(after.channel.id),
                        "user_id": int(user_ref.id),
                        "started_at": now.isoformat(),
                    })
                    logger.debug(f"Queued new voice session start for user {user_ref.id} in guild {guild_id}")

        except Exception as e:
            logger.error(f"Error queueing voice state event: {e}")


def setup(bot):
    VoiceEvents(bot)
