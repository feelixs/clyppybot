from dataclasses import dataclass
from typing import List, Optional
from interactions import Guild

from ..api_client import get_api_client


@dataclass
class ServerStats:
    """Server statistics summary."""

    guild_id: int
    guild_name: str
    member_count: int
    online_count: Optional[int]
    boost_level: int
    boost_count: int

    # Period stats
    messages_today: int
    messages_week: int
    voice_minutes_today: int
    voice_minutes_week: int
    gaming_minutes_today: int
    gaming_minutes_week: int
    active_users_today: int
    active_users_week: int

    # Growth
    members_joined_week: int
    members_left_week: int
    net_growth_week: int
    growth_percentage: float


@dataclass
class ChannelStats:
    """Channel statistics summary."""

    channel_id: int
    channel_name: str
    messages_today: int
    messages_week: int
    messages_month: int


@dataclass
class UserStats:
    """User statistics summary."""

    user_id: int
    username: str
    messages_today: int
    messages_week: int
    messages_month: int
    voice_minutes_today: int
    voice_minutes_week: int
    voice_minutes_month: int
    gaming_minutes_today: int
    gaming_minutes_week: int
    gaming_minutes_month: int
    rank_messages: int
    rank_voice: int
    rank_gaming: int


@dataclass
class LeaderboardEntry:
    """Leaderboard entry."""

    user_id: int
    username: str
    value: int
    rank: int


class StatsService:
    """Service for aggregating and retrieving statistics."""

    @staticmethod
    async def get_server_stats(guild: Guild) -> ServerStats:
        """Get comprehensive server statistics."""
        api = get_api_client()
        guild_id = int(guild.id)

        # Ensure guild exists in database
        guild_record = await api.get_guild(guild_id)
        if not guild_record:
            await api.upsert_guild(
                guild_id=guild_id,
                name=guild.name,
                icon_hash=guild.icon.hash if guild.icon else None,
                member_count=guild.member_count or 0,
                boost_level=guild.premium_tier or 0,
                boost_count=guild.premium_subscription_count or 0,
            )

        # Get stats from API
        data = await api.get_server_stats(guild_id)

        return ServerStats(
            guild_id=guild_id,
            guild_name=data["guild_name"],
            member_count=data["member_count"],
            online_count=None,
            boost_level=data["boost_level"],
            boost_count=data["boost_count"],
            messages_today=data["messages_today"],
            messages_week=data["messages_week"],
            voice_minutes_today=data["voice_minutes_today"],
            voice_minutes_week=data["voice_minutes_week"],
            gaming_minutes_today=data.get("gaming_minutes_today", 0),
            gaming_minutes_week=data.get("gaming_minutes_week", 0),
            active_users_today=data["active_users_today"],
            active_users_week=data["active_users_week"],
            members_joined_week=data["members_joined_week"],
            members_left_week=data["members_left_week"],
            net_growth_week=data["net_growth_week"],
            growth_percentage=data["growth_percentage"],
        )

    @staticmethod
    async def get_channel_stats(
        guild_id: int,
        channel_id: int,
        channel_name: str,
    ) -> ChannelStats:
        """Get statistics for a specific channel."""
        api = get_api_client()
        data = await api.get_channel_stats(guild_id, channel_id)

        return ChannelStats(
            channel_id=channel_id,
            channel_name=channel_name,
            messages_today=data["messages_today"],
            messages_week=data["messages_week"],
            messages_month=data["messages_month"],
        )

    @staticmethod
    async def get_user_stats(
        guild_id: int,
        user_id: int,
        username: str,
    ) -> UserStats:
        """Get statistics for a specific user."""
        api = get_api_client()
        data = await api.get_user_stats(guild_id, user_id)

        return UserStats(
            user_id=user_id,
            username=username,
            messages_today=data["messages_today"],
            messages_week=data["messages_week"],
            messages_month=data["messages_month"],
            voice_minutes_today=data["voice_minutes_today"],
            voice_minutes_week=data["voice_minutes_week"],
            voice_minutes_month=data["voice_minutes_month"],
            gaming_minutes_today=data.get("gaming_minutes_today", 0),
            gaming_minutes_week=data.get("gaming_minutes_week", 0),
            gaming_minutes_month=data.get("gaming_minutes_month", 0),
            rank_messages=data["rank_messages"],
            rank_voice=data["rank_voice"],
            rank_gaming=data.get("rank_gaming", 0),
        )

    @staticmethod
    async def get_message_leaderboard(
        guild_id: int,
        period: str = "week",
        limit: int = 10,
    ) -> List[LeaderboardEntry]:
        """Get message leaderboard."""
        api = get_api_client()
        entries = await api.get_message_leaderboard(guild_id, period, limit)

        return [
            LeaderboardEntry(
                user_id=entry["user_id"],
                username=entry.get("username", ""),
                value=entry["value"],
                rank=entry["rank"],
            )
            for entry in entries
        ]

    @staticmethod
    async def get_voice_leaderboard(
        guild_id: int,
        period: str = "week",
        limit: int = 10,
    ) -> List[LeaderboardEntry]:
        """Get voice time leaderboard."""
        api = get_api_client()
        entries = await api.get_voice_leaderboard(guild_id, period, limit)

        return [
            LeaderboardEntry(
                user_id=entry["user_id"],
                username=entry.get("username", ""),
                value=entry["value"],
                rank=entry["rank"],
            )
            for entry in entries
        ]

    @staticmethod
    async def get_game_leaderboard(
        guild_id: int,
        period: str = "week",
        limit: int = 10,
    ) -> List[LeaderboardEntry]:
        """Get game time leaderboard."""
        api = get_api_client()
        entries = await api.get_game_leaderboard(guild_id, period, limit)

        return [
            LeaderboardEntry(
                user_id=entry["user_id"],
                username=entry.get("username", ""),
                value=entry["value"],
                rank=entry["rank"],
            )
            for entry in entries
        ]

    @staticmethod
    async def get_invite_leaderboard(
        guild_id: int,
        period: str = "all",
        limit: int = 10,
    ) -> List[LeaderboardEntry]:
        """Get invite leaderboard."""
        api = get_api_client()
        data = await api.get_invite_leaderboard(guild_id, period, limit)
        entries = data.get("entries", [])

        return [
            LeaderboardEntry(
                user_id=entry["user_id"],
                username="",
                value=entry["invite_count"],
                rank=i + 1,
            )
            for i, entry in enumerate(entries)
        ]
