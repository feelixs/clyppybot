"""HTTP client for bot to communicate with the web API."""

from interactions import Member, User

from datetime import datetime
from typing import Optional, List
import httpx

from .config import config
from .logging_config import get_logger

logger = get_logger("insightbot.api_client")


class APIClient:
    """Client for the bot to send data to the web API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "X-Bot-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Optional[dict]:
        """Make an API request."""
        client = await self._get_client()
        try:
            response = await client.request(
                method,
                endpoint,
                json=json,
                params=params,
            )
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"API error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"API request failed: {e}")
            raise

    # Guild operations
    async def upsert_guild(
        self,
        guild_id: int,
        name: str,
        icon_hash: Optional[str] = None,
        member_count: int = 0,
        boost_level: int = 0,
        boost_count: int = 0,
    ) -> bool:
        """Create or update a guild. Returns True if inserted (new), False if updated."""
        result = await self._request(
            "POST",
            "/api/internal/guilds",
            json={
                "guild_id": guild_id,
                "name": name,
                "icon_hash": icon_hash,
                "member_count": member_count,
                "boost_level": boost_level,
                "boost_count": boost_count,
            },
        )
        return result.get("inserted", False)

    async def get_guild(self, guild_id: int) -> Optional[dict]:
        """Get guild by ID."""
        try:
            return await self._request("GET", f"/api/internal/guilds/{guild_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def update_guild_member_count(self, guild_id: int, member_count: int) -> None:
        """Update guild member count."""
        await self._request(
            "PATCH",
            f"/api/internal/guilds/{guild_id}/member-count",
            json={"member_count": member_count},
        )

    # Discord user operations
    async def upsert_discord_user(
        self,
        user: Member | User,
        global_name: Optional[str] = None
    ) -> None:
        """Upsert global Discord user data."""
        user = user.user if isinstance(user, Member) else user
        await self._request(
            "POST",
            "/api/internal/discord-users",
            json={
                "user_id": user.id,
                "username": user.username,
                "global_name": global_name,
                "avatar_hash": user.avatar.hash,
            },
        )

    async def bulk_upsert_discord_users(
        self,
        users: List[dict],
    ) -> int:
        """Bulk upsert Discord user data. Returns count upserted."""
        if not users:
            return 0
        result = await self._request(
            "POST",
            "/api/internal/discord-users/bulk",
            json={"users": users},
        )
        return result.get("count", 0)

    # Member operations
    async def upsert_member(
        self,
        guild_id: int,
        user: Member | User,
        display_name: Optional[str] = None,
        joined_at: Optional[datetime] = None,
        is_bot: bool = False,
    ) -> None:
        """Create or update a member."""
        user = user.user if isinstance(user, Member) else user
        await self.upsert_discord_user(
            user=user,
            global_name=user.global_name,
        )
        await self._request(
            "POST",
            "/api/internal/members",
            json={
                "guild_id": guild_id,
                "user_id": user.id,
                "display_name": display_name,
                "joined_at": joined_at.isoformat() if joined_at else None,
                "is_bot": is_bot,
            },
        )

    async def bulk_upsert_members(
        self, members: List[dict], guild=None, guild_id: int = None
    ) -> int:
        """Bulk create or update members. Returns count upserted.

        Args:
            members: List of member data dictionaries
            guild: Discord guild object (optional, for logging)
            guild_id: Guild ID (optional, used if guild not provided)
        """
        try:
            if not members:
                return 0
            gid = guild_id or (int(guild.id) if guild else None)
            result = await self._request(
                "POST",
                "/api/internal/members/bulk",
                json={"members": members},
            )
            count = result.get("count", 0)
            logger.debug(f"Synced {count} members for guild {gid}")
            return count
        except Exception as e:
            gid = guild_id or (int(guild.id) if guild else "unknown")
            logger.error(f"Failed to sync members for guild {gid}: {e}")
            return 0

    async def delete_member(self, guild_id: int, user_id: int) -> None:
        """Delete a member."""
        await self._request("DELETE", f"/api/internal/members/{guild_id}/{user_id}")

    async def log_member_event(
        self,
        guild_id: int,
        user_id: int,
        event_type: str,
    ) -> None:
        """Log a member join/leave event."""
        await self._request(
            "POST",
            "/api/internal/member-events",
            json={
                "guild_id": guild_id,
                "user_id": user_id,
                "event_type": event_type,
            },
        )

    # Message stats
    async def increment_message_count(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        hour_bucket: datetime,
        message_count: int = 1,
        character_count: int = 0,
    ) -> None:
        """Increment message count for tracking."""
        await self._request(
            "POST",
            "/api/internal/messages",
            json={
                "guild_id": guild_id,
                "channel_id": channel_id,
                "user_id": user_id,
                "hour_bucket": hour_bucket.isoformat(),
                "message_count": message_count,
                "character_count": character_count,
            },
        )

    # Voice sessions
    async def start_voice_session(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        started_at: datetime,
    ) -> int:
        """Start a voice session."""
        result = await self._request(
            "POST",
            "/api/internal/voice/start",
            json={
                "guild_id": guild_id,
                "channel_id": channel_id,
                "user_id": user_id,
                "started_at": started_at.isoformat(),
            },
        )
        return result["session_id"]

    async def end_voice_session(
        self,
        guild_id: int,
        user_id: int,
        ended_at: datetime,
    ) -> Optional[int]:
        """End a voice session."""
        result = await self._request(
            "POST",
            "/api/internal/voice/end",
            json={
                "guild_id": guild_id,
                "user_id": user_id,
                "ended_at": ended_at.isoformat(),
            },
        )
        return result.get("duration_seconds") if result else None

    # Game sessions
    async def start_game_session(
        self,
        guild_id: int,
        user_id: int,
        game_name: str,
        started_at: datetime,
        application_id: Optional[int] = None,
    ) -> int:
        """Start a game session."""
        result = await self._request(
            "POST",
            "/api/internal/games/start",
            json={
                "guild_id": guild_id,
                "user_id": user_id,
                "game_name": game_name,
                "application_id": application_id,
                "started_at": started_at.isoformat(),
            },
        )
        return result["session_id"]

    async def end_game_session(
        self,
        guild_id: int,
        user_id: int,
        ended_at: datetime,
    ) -> Optional[dict]:
        """End a game session."""
        result = await self._request(
            "POST",
            "/api/internal/games/end",
            json={
                "guild_id": guild_id,
                "user_id": user_id,
                "ended_at": ended_at.isoformat(),
            },
        )
        return result

    async def get_game_leaderboard(
        self,
        guild_id: int,
        period: str = "week",
        limit: int = 10,
    ) -> List[dict]:
        """Get games leaderboard (by player playtime)."""
        result = await self._request(
            "GET",
            f"/api/internal/leaderboard/{guild_id}/games",
            params={"period": period, "limit": limit},
        )
        return result.get("entries", [])

    async def get_top_games(
        self,
        guild_id: int,
        period: str = "week",
        limit: int = 20,
    ) -> List[dict]:
        """Get top games leaderboard (by total playtime)."""
        result = await self._request(
            "GET",
            f"/api/internal/leaderboard/{guild_id}/top-games",
            params={"period": period, "limit": limit},
        )
        return result.get("entries", [])

    async def get_user_games(
        self,
        guild_id: int,
        user_id: int,
        period: str = "month",
    ) -> List[dict]:
        """Get games played by a specific user."""
        result = await self._request(
            "GET",
            f"/api/internal/stats/user/{guild_id}/{user_id}/games",
            params={"period": period},
        )
        return result.get("games", [])

    async def get_server_game_stats(
        self,
        guild_id: int,
        period: str = "week",
    ) -> dict:
        """Get server-wide game statistics."""
        return await self._request(
            "GET",
            f"/api/internal/stats/server/{guild_id}/games",
            params={"period": period},
        )

    async def get_game_detail(
        self,
        guild_id: int,
        game_id: int,
        period: str = "month",
    ) -> dict:
        """Get detailed information about a specific game."""
        return await self._request(
            "GET",
            f"/api/internal/stats/game/{guild_id}/{game_id}",
            params={"period": period},
        )

    # Stats retrieval
    async def get_server_stats(self, guild_id: int) -> dict:
        """Get server statistics."""
        return await self._request("GET", f"/api/internal/stats/server/{guild_id}")

    async def get_channel_stats(self, guild_id: int, channel_id: int) -> dict:
        """Get channel statistics."""
        return await self._request(
            "GET",
            f"/api/internal/stats/channel/{guild_id}/{channel_id}",
        )

    async def get_user_stats(self, guild_id: int, user_id: int) -> dict:
        """Get user statistics."""
        return await self._request(
            "GET",
            f"/api/internal/stats/user/{guild_id}/{user_id}",
        )

    async def get_message_leaderboard(
        self,
        guild_id: int,
        period: str = "week",
        limit: int = 10,
    ) -> List[dict]:
        """Get message leaderboard."""
        result = await self._request(
            "GET",
            f"/api/internal/leaderboard/{guild_id}/messages",
            params={"period": period, "limit": limit},
        )
        return result.get("entries", [])

    async def get_voice_leaderboard(
        self,
        guild_id: int,
        period: str = "week",
        limit: int = 10,
    ) -> List[dict]:
        """Get voice leaderboard."""
        result = await self._request(
            "GET",
            f"/api/internal/leaderboard/{guild_id}/voice",
            params={"period": period, "limit": limit},
        )
        return result.get("entries", [])

    # Counter operations
    async def get_all_counters(self) -> List[dict]:
        """Get all counters."""
        result = await self._request("GET", "/api/internal/counters")
        return result or []

    async def get_guild_counters(self, guild_id: int) -> List[dict]:
        """Get counters for a guild."""
        result = await self._request("GET", f"/api/internal/counters/{guild_id}")
        return result or []

    async def create_counter(
        self,
        guild_id: int,
        channel_id: int,
        counter_type: str,
        template: str,
        role_id: Optional[int] = None,
        goal_target: Optional[int] = None,
    ) -> dict:
        """Create a counter."""
        return await self._request(
            "POST",
            "/api/internal/counters",
            json={
                "guild_id": guild_id,
                "channel_id": channel_id,
                "counter_type": counter_type,
                "template": template,
                "role_id": role_id,
                "goal_target": goal_target,
            },
        )

    async def update_counter_value(self, channel_id: int, value: int) -> None:
        """Update counter value."""
        await self._request(
            "PATCH",
            f"/api/internal/counters/{channel_id}/value",
            json={"value": value},
        )

    async def delete_counter(self, channel_id: int) -> bool:
        """Delete a counter."""
        try:
            await self._request("DELETE", f"/api/internal/counters/{channel_id}")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            raise

    async def get_counter_by_channel(self, channel_id: int) -> Optional[dict]:
        """Get counter by channel ID."""
        try:
            return await self._request("GET", f"/api/internal/counters/channel/{channel_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def can_create_counter(self, guild_id: int) -> dict:
        """Check if guild can create a new counter based on tier limits."""
        return await self._request("GET", f"/api/internal/counters/{guild_id}/can-create")

    async def get_active_voice_count(self, guild_id: int) -> int:
        """Get active voice session count."""
        result = await self._request("GET", f"/api/internal/voice/active/{guild_id}")
        return result.get("count", 0)

    async def get_open_voice_sessions(self, guild_id: int) -> List[dict]:
        """Get all open voice sessions for a guild."""
        result = await self._request("GET", f"/api/internal/voice/open/{guild_id}")
        return result or []

    async def bulk_end_voice_sessions(self, session_ids: List[int], ended_at: datetime) -> int:
        """End multiple voice sessions. Returns count closed."""
        result = await self._request(
            "POST",
            "/api/internal/voice/bulk-end",
            json={
                "session_ids": session_ids,
                "ended_at": ended_at.isoformat(),
            },
        )
        return result.get("closed_count", 0) if result else 0

    async def get_open_game_sessions(self, guild_id: int) -> List[dict]:
        """Get all open game sessions for a guild."""
        result = await self._request("GET", f"/api/internal/games/open/{guild_id}")
        return result or []

    async def bulk_end_game_sessions(self, session_ids: List[int], ended_at: datetime) -> int:
        """End multiple game sessions. Returns count closed."""
        result = await self._request(
            "POST",
            "/api/internal/games/bulk-end",
            json={
                "session_ids": session_ids,
                "ended_at": ended_at.isoformat(),
            },
        )
        return result.get("closed_count", 0) if result else 0

    # Digest operations
    async def get_digest_config(self, guild_id: int) -> Optional[dict]:
        """Get digest configuration."""
        try:
            return await self._request("GET", f"/api/internal/digest/{guild_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def upsert_digest_config(
        self,
        guild_id: int,
        channel_id: int,
        day_of_week: int = 0,
        hour_utc: int = 12,
        enabled: bool = True,
    ) -> None:
        """Create or update digest configuration."""
        await self._request(
            "POST",
            "/api/internal/digest",
            json={
                "guild_id": guild_id,
                "channel_id": channel_id,
                "day_of_week": day_of_week,
                "hour_utc": hour_utc,
                "enabled": enabled,
            },
        )

    async def set_digest_enabled(self, guild_id: int, enabled: bool) -> None:
        """Enable or disable digest."""
        await self._request(
            "PATCH",
            f"/api/internal/digest/{guild_id}/enabled",
            json={"enabled": enabled},
        )

    async def mark_digest_sent(self, guild_id: int) -> None:
        """Mark digest as sent."""
        await self._request("POST", f"/api/internal/digest/{guild_id}/sent")

    async def get_due_digests(self, day_of_week: int, hour_utc: int) -> List[dict]:
        """Get digests due to be sent."""
        result = await self._request(
            "GET",
            "/api/internal/digest/due",
            params={"day_of_week": day_of_week, "hour_utc": hour_utc},
        )
        return result or []

    async def get_digest_data(self, guild_id: int) -> dict:
        """Get digest data for a guild."""
        return await self._request("GET", f"/api/internal/digest/{guild_id}/data")

    # Subscription operations
    async def get_subscription(self, guild_id: int) -> dict:
        """Get subscription for guild. Returns tier=0 if none exists."""
        return await self._request("GET", f"/api/internal/subscriptions/{guild_id}")

    async def upsert_subscription(
        self,
        guild_id: int,
        tier: int,
        expires_at: Optional[datetime] = None,
        payment_id: Optional[str] = None,
    ) -> None:
        """Create or update subscription."""
        await self._request(
            "POST",
            "/api/internal/subscriptions",
            json={
                "guild_id": guild_id,
                "tier": tier,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "payment_id": payment_id,
            },
        )

    async def get_tier(self, guild_id: int) -> int:
        """Get subscription tier for guild."""
        result = await self._request("GET", f"/api/internal/subscriptions/{guild_id}/tier")
        return result.get("tier", 0)

    async def use_preview(self, guild_id: int) -> dict:
        """Check and consume a preview. Returns allowed, remaining, limit, resets_at."""
        return await self._request("POST", f"/api/internal/digest/{guild_id}/preview-used")

    # Analytics operations
    async def submit_hourly_analytics(
        self,
        timestamp: datetime,
        guild_stats: dict,
        channel_stats: dict,
    ) -> dict:
        """Submit hourly analytics data.

        Args:
            timestamp: The hour bucket timestamp
            guild_stats: Dict of guild_id -> stats dict
            channel_stats: Dict of guild_id -> channel_id -> stats dict

        Returns:
            Response with status and counts processed
        """
        return await self._request(
            "POST",
            "/api/internal/analytics/hourly",
            json={
                "timestamp": timestamp.isoformat(),
                "guild_stats": guild_stats,
                "channel_stats": channel_stats,
            },
        )

    # Invite tracking operations
    async def record_member_invite(
        self,
        guild_id: int,
        member_id: int,
        invited_by_id: Optional[int],
        invite_code: Optional[str],
        joined_at: datetime,
    ) -> dict:
        """Record which invite was used when a member joined.

        Args:
            guild_id: The guild ID
            member_id: The joining member's ID
            invited_by_id: The inviter's user ID (None if unknown)
            invite_code: The invite code used (None if unknown)
            joined_at: When the member joined

        Returns:
            Response with status
        """
        return await self._request(
            "POST",
            "/api/internal/invites/member-join",
            json={
                "guild_id": guild_id,
                "member_id": member_id,
                "invited_by_id": invited_by_id,
                "invite_code": invite_code,
                "joined_at": joined_at.isoformat(),
            },
        )

    async def get_invite_leaderboard(
        self,
        guild_id: int,
        period: str = "all",
        limit: int = 10,
    ) -> List[dict]:
        """Get top inviters for a guild.

        Args:
            guild_id: The guild ID
            period: Time period (week, month, all)
            limit: Maximum entries to return

        Returns:
            List of leaderboard entries
        """
        result = await self._request(
            "GET",
            f"/api/internal/invites/leaderboard/{guild_id}",
            params={"period": period, "limit": limit},
        )
        return result.get("entries", [])

    async def get_user_invites(
        self,
        guild_id: int,
        user_id: int,
        limit: int = 50,
    ) -> dict:
        """Get members invited by a specific user.

        Args:
            guild_id: The guild ID
            user_id: The inviter's user ID
            limit: Maximum entries to return

        Returns:
            Dict with total_invites and invited_members list
        """
        return await self._request(
            "GET",
            f"/api/internal/invites/user/{guild_id}/{user_id}",
            params={"limit": limit},
        )

    # Topic tracking operations
    async def get_topic_aliases(self) -> List[dict]:
        """Get all topic aliases for caching.

        Returns:
            List of alias records with topic_id, category_id, alias, is_anchor, is_ambiguous, full_phrase
        """
        result = await self._request("GET", "/api/internal/topics/aliases")
        return result or []

    async def get_context_words(self) -> List[dict]:
        """Get all category context words for tier-based matching.

        Returns:
            List of category context word mappings with category_id, category_name, words
        """
        result = await self._request("GET", "/api/internal/topics/context-words")
        return result or []

    async def get_stopwords(self) -> List[dict]:
        """Get all stopwords for filtering unknown words.

        Returns:
            List of stopword records with word, language
        """
        result = await self._request("GET", "/api/internal/topics/stopwords")
        return result or []

    async def submit_topic_data(
        self,
        date: datetime,
        topic_mentions: dict,
        unknown_words: dict,
        word_frequency: dict = None,
    ) -> dict:
        """Submit topic tracking data.

        Args:
            date: The date for the data
            topic_mentions: Dict of guild_id -> channel_id -> list of mention data
            unknown_words: Dict of guild_id -> channel_id -> list of unknown word data
            word_frequency: Dict of guild_id -> channel_id -> list of word frequency data
                           (for phrase correlation detection, pre-filtered to 10+ mentions)

        Returns:
            Response with status and counts processed
        """
        payload = {
            "date": date.strftime("%Y-%m-%d"),
            "topic_mentions": topic_mentions,
            "unknown_words": unknown_words,
        }
        if word_frequency:
            payload["word_frequency"] = word_frequency

        return await self._request(
            "POST",
            "/api/internal/topics/data",
            json=payload,
        )

    async def submit_word_frequency(
        self,
        date: datetime,
        word_frequency: dict,
    ) -> dict:
        """Submit word frequency data for phrase correlation detection.

        Called hourly to batch database writes efficiently.

        Args:
            date: The date for the data
            word_frequency: Dict of guild_id -> channel_id -> list of word frequency data
                           (pre-filtered to 10+ mentions per guild)

        Returns:
            Response with status and counts processed
        """
        payload = {
            "date": date.strftime("%Y-%m-%d"),
            "word_frequency": word_frequency,
        }

        return await self._request(
            "POST",
            "/api/internal/topics/word-frequency",
            json=payload,
        )

    async def get_trending_topics(
        self,
        guild_id: int,
        days: int = 7,
        limit: int = 10,
    ) -> dict:
        """Get trending topics for a guild.

        Args:
            guild_id: The guild ID
            days: Number of days to look back
            limit: Maximum topics to return

        Returns:
            Dict with guild_id, period_days, and topics list
        """
        return await self._request(
            "GET",
            f"/api/internal/topics/trending/{guild_id}",
            params={"days": days, "limit": limit},
        )

    async def get_emerging_topics(
        self,
        guild_id: int,
        min_mentions: int = 5,
        limit: int = 20,
    ) -> dict:
        """Get emerging unknown words that might be new topics.

        Args:
            guild_id: The guild ID
            min_mentions: Minimum mention count threshold
            limit: Maximum words to return

        Returns:
            Dict with guild_id and words list
        """
        return await self._request(
            "GET",
            f"/api/internal/topics/emerging/{guild_id}",
            params={"min_mentions": min_mentions, "limit": limit},
        )

    async def get_channel_topics(
        self,
        guild_id: int,
        channel_id: int,
        days: int = 7,
        limit: int = 10,
    ) -> dict:
        """Get trending topics for a specific channel.

        Args:
            guild_id: The guild ID
            channel_id: The channel ID
            days: Number of days to look back
            limit: Maximum topics to return

        Returns:
            Dict with guild_id, channel_id, period_days, and topics list
        """
        return await self._request(
            "GET",
            f"/api/internal/topics/channel/{guild_id}/{channel_id}",
            params={"days": days, "limit": limit},
        )

    async def get_topic_stats(
        self,
        guild_id: int,
    ) -> dict:
        """Get overall topic statistics for a guild.

        Args:
            guild_id: The guild ID

        Returns:
            Dict with statistics including unique_topics, total_mentions,
            top_category, unknown_words_count, categories
        """
        return await self._request(
            "GET",
            f"/api/internal/topics/stats/{guild_id}",
        )


# Global client instance
_client: Optional[APIClient] = None


def get_api_client() -> APIClient:
    """Get the global API client instance."""
    global _client
    if _client is None:
        _client = APIClient(config.api_base_url, config.bot_api_key)
    return _client


async def close_api_client() -> None:
    """Close the global API client."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
