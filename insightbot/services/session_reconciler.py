"""Session reconciliation service for syncing database state with Discord on startup."""

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timezone

from interactions import ActivityType

from ..api_client import get_api_client
from ..logging_config import get_logger
from .event_queue import get_event_queue, EVENT_USER_LAST_ONLINE

logger = get_logger("insightbot.services.reconciler")

# Gateway rate limit: 120 requests per 60s per shard.
# Use a conservative budget to leave headroom for other gateway ops.
CHUNK_REQUESTS_PER_WINDOW = 90
WINDOW_SECONDS = 60


class _ShardRateLimiter:
    """Token-bucket rate limiter scoped per shard."""

    def __init__(self, rate: int = CHUNK_REQUESTS_PER_WINDOW, per: float = WINDOW_SECONDS):
        self._rate = rate
        self._per = per
        self._semaphores: dict[int, asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, shard_id: int) -> None:
        async with self._lock:
            if shard_id not in self._semaphores:
                self._semaphores[shard_id] = asyncio.Semaphore(self._rate)

        sem = self._semaphores[shard_id]
        await sem.acquire()
        # Release the token after the window elapses
        asyncio.get_event_loop().call_later(self._per, sem.release)


class SessionReconciler:
    """Reconciles database sessions with Discord's actual state on startup."""

    @staticmethod
    async def reconcile_guild(guild, rate_limiter: _ShardRateLimiter, shard_id: int) -> dict:
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

        # Rate-limit the gateway chunk request per shard
        await rate_limiter.acquire(shard_id)
        await guild.gateway_chunk(wait=True, presences=True)

        if not guild.members:
            logger.warning(
                f"Guild {guild.name} ({guild_id}) has no cached members, skipping reconciliation"
            )
            return {"voice_closed": 0, "game_closed": 0}

        # Build sets of users currently in voice / playing games
        users_in_voice = set()
        users_playing_games = {}  # {user_id: game_name}
        users_online = []  # Users to update last_online for

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

            # Capture online presence state
            if member.status and member.status.value in ('online', 'idle', 'dnd'):
                users_online.append(user_id)

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

        # Capture initial presence states for currently online users
        if users_online:
            queue = get_event_queue()
            for user_id in users_online:
                await queue.enqueue(EVENT_USER_LAST_ONLINE, {
                    "user_id": user_id,
                })
            logger.info(
                f"Guild {guild.name}: queued {len(users_online)} initial presence states"
            )

        return {
            "voice_closed": voice_closed,
            "game_closed": game_closed,
        }

    @staticmethod
    async def reconcile_all(bot) -> dict:
        """
        Reconcile sessions across all guilds.

        Groups guilds by shard and processes them concurrently with
        per-shard gateway rate limiting.

        Returns:
            dict with total 'voice_closed' and 'game_closed' counts
        """
        rate_limiter = _ShardRateLimiter()
        total_shards = getattr(bot, 'total_shards', 1) or 1

        # Group guilds by shard
        guilds_by_shard: dict[int, list] = defaultdict(list)
        for guild in bot.guilds:
            shard_id = (int(guild.id) >> 22) % total_shards
            guilds_by_shard[shard_id].append(guild)

        logger.info(
            f"Reconciling {len(bot.guilds)} guilds across {len(guilds_by_shard)} shard(s)"
        )

        total_voice = 0
        total_game = 0
        start = time.monotonic()

        async def _reconcile(guild, shard_id: int) -> dict:
            try:
                return await SessionReconciler.reconcile_guild(guild, rate_limiter, shard_id)
            except Exception as e:
                logger.error(f"Failed to reconcile guild {guild.name}: {e}")
                return {"voice_closed": 0, "game_closed": 0}

        # Launch all guilds concurrently; the rate limiter gates per-shard throughput
        tasks = []
        for shard_id, guilds in guilds_by_shard.items():
            for guild in guilds:
                tasks.append(_reconcile(guild, shard_id))

        results = await asyncio.gather(*tasks)
        for result in results:
            total_voice += result["voice_closed"]
            total_game += result["game_closed"]

        elapsed = time.monotonic() - start
        logger.info(f"Reconciliation finished in {elapsed:.1f}s")

        return {"voice_closed": total_voice, "game_closed": total_game}
