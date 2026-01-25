from datetime import datetime, timezone

from interactions import Extension, listen
from interactions.api.events import VoiceStateUpdate

from ..logging_config import get_logger
from ..api_client import get_api_client

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
            api = get_api_client()

            # User joined a voice channel
            if not before or not before.channel:
                if after.channel:
                    # Upsert user to discord_users
                    member = after.member
                    if member:
                        await api.upsert_discord_user(
                            user=user_ref,
                            global_name=member.global_name,
                        )

                    # Start a new session
                    await api.start_voice_session(
                        guild_id=guild_id,
                        channel_id=int(after.channel.id),
                        user_id=user_ref.id,
                        started_at=now,
                    )
                    logger.debug(f"Started voice session for user {user_ref.id} in guild {guild_id}")

            # User left a voice channel
            elif before.channel and (not after or not after.channel or after.channel.id != before.channel.id):
                # End the current session
                duration = await api.end_voice_session(
                    guild_id=guild_id,
                    user_id=user_ref.id,
                    ended_at=now,
                )
                if duration:
                    logger.debug(
                        f"Ended voice session for user {user_ref.id} in guild {guild_id} "
                        f"(duration: {duration}s)"
                    )

                # If they moved to another channel, start a new session
                if after and after.channel and (not before.channel or after.channel.id != before.channel.id):
                    await api.start_voice_session(
                        guild_id=guild_id,
                        channel_id=int(after.channel.id),
                        user_id=user_ref.id,
                        started_at=now,
                    )
                    logger.debug(
                        f"Started new voice session for user {user_ref.id} in guild {guild_id}"
                    )

        except Exception as e:
            logger.error(f"Error tracking voice state: {e}")


def setup(bot):
    VoiceEvents(bot)
