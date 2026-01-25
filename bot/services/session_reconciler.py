"""Session reconciliation service for syncing database state with Discord on startup."""

from datetime import datetime, timezone

from interactions import ActivityType

from ..api_client import get_api_client
from ..logging_config import get_logger

logger = get_logger("insightbot.services.reconciler")


class SessionReconciler:
    """Reconciles database sessions with Discord's actual state on startup."""

    @staticmethod
    async def reconcile_guild(guild) -> dict:
        """
        Reconcile all sessions for a guild.

        Compares open sessions in the database against Discord's current state
        and closes any sessions that are no longer valid.

        Returns:
            dict with 'voice_closed' and 'game_closed' counts
        """
        api = get_api_client()
        now = datetime.now(timezone.utc)
        guild_id = int(guild.id)

        # Check if we have member data
        if not guild.members:
            logger.warning(
                f"Guild {guild.name} ({guild_id}) has no cached members, skipping reconciliation"
            )
            return {"voice_closed": 0, "game_closed": 0}

        # Build sets of users currently in voice / playing games
        users_in_voice = set()
        users_playing_games = {}  # {user_id: game_name}

        for member in guild.members:
            if member.bot:
                continue
            user_id = int(member.id)

            # Check voice state
            if member.voice and member.voice.channel:
                users_in_voice.add(user_id)

            # Check game activity from presence
            if member.user.activities:
                for activity in member.user.activities:
                    if activity.type == ActivityType.GAME:
                        users_playing_games[user_id] = activity.name
                        break

        # Get open sessions from database
        open_voice = await api.get_open_voice_sessions(guild_id)
        open_games = await api.get_open_game_sessions(guild_id)

        # Find voice sessions to close
        voice_to_close = []
        for session in open_voice:
            if session["user_id"] not in users_in_voice:
                voice_to_close.append(session["session_id"])

        # Find game sessions to close
        game_to_close = []
        for session in open_games:
            user_id = session["user_id"]
            # Close if user not playing ANY game, or playing a DIFFERENT game
            if user_id not in users_playing_games:
                game_to_close.append(session["session_id"])
            elif users_playing_games[user_id] != session["game_name"]:
                game_to_close.append(session["session_id"])

        # Bulk close sessions
        voice_closed = 0
        game_closed = 0

        if voice_to_close:
            voice_closed = await api.bulk_end_voice_sessions(voice_to_close, now)
            logger.info(
                f"Guild {guild.name}: closed {voice_closed} stale voice sessions"
            )

        if game_to_close:
            game_closed = await api.bulk_end_game_sessions(game_to_close, now)
            logger.info(
                f"Guild {guild.name}: closed {game_closed} stale game sessions"
            )

        return {
            "voice_closed": voice_closed,
            "game_closed": game_closed,
        }

    @staticmethod
    async def reconcile_all(bot) -> dict:
        """
        Reconcile sessions across all guilds.

        Returns:
            dict with total 'voice_closed' and 'game_closed' counts
        """
        total_voice = 0
        total_game = 0

        for guild in bot.guilds:
            try:
                result = await SessionReconciler.reconcile_guild(guild)
                total_voice += result["voice_closed"]
                total_game += result["game_closed"]
            except Exception as e:
                logger.error(f"Failed to reconcile guild {guild.name}: {e}")

        return {"voice_closed": total_voice, "game_closed": total_game}
