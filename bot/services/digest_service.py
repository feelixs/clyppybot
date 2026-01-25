from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from interactions import Guild, Embed

from ..logging_config import get_logger
from ..api_client import get_api_client

logger = get_logger("insightbot.services.digest")


@dataclass
class DigestData:
    """Weekly digest data."""

    guild_id: int
    guild_name: str
    period_start: datetime
    period_end: datetime

    # Growth
    member_count: int
    members_joined: int
    members_left: int
    net_growth: int
    growth_percentage: float

    # Activity
    total_messages: int
    previous_messages: int
    message_change_pct: float
    total_voice_minutes: int
    previous_voice_minutes: int
    voice_change_pct: float
    active_users: int

    # Top contributors
    top_message_users: List[tuple[int, int]]
    top_voice_users: List[tuple[int, int]]
    top_channels: List[tuple[int, int]]

    # AI insights
    ai_insight: Optional[str]


class DigestService:
    """Service for generating weekly digests."""

    @staticmethod
    async def configure_digest(
        guild_id: int,
        channel_id: int,
        day_of_week: int = 0,
        hour_utc: int = 12,
    ) -> None:
        """Configure digest settings for a guild."""
        api = get_api_client()
        await api.upsert_digest_config(
            guild_id=guild_id,
            channel_id=channel_id,
            day_of_week=day_of_week,
            hour_utc=hour_utc,
            enabled=True,
        )

    @staticmethod
    async def disable_digest(guild_id: int) -> None:
        """Disable digest for a guild."""
        api = get_api_client()
        await api.set_digest_enabled(guild_id, False)

    @staticmethod
    async def get_digest_data(guild: Guild) -> DigestData:
        """Generate digest data for a guild."""
        api = get_api_client()
        data = await api.get_digest_data(int(guild.id))

        return DigestData(
            guild_id=data["guild_id"],
            guild_name=data["guild_name"],
            period_start=datetime.fromisoformat(data["period_start"]),
            period_end=datetime.fromisoformat(data["period_end"]),
            member_count=data["member_count"],
            members_joined=data["members_joined"],
            members_left=data["members_left"],
            net_growth=data["net_growth"],
            growth_percentage=data["growth_percentage"],
            total_messages=data["total_messages"],
            previous_messages=data["previous_messages"],
            message_change_pct=data["message_change_pct"],
            total_voice_minutes=data["total_voice_minutes"],
            previous_voice_minutes=data["previous_voice_minutes"],
            voice_change_pct=data["voice_change_pct"],
            active_users=data["active_users"],
            top_message_users=[(int(x[0]), int(x[1])) for x in data["top_message_users"]],
            top_voice_users=[(int(x[0]), int(x[1])) for x in data["top_voice_users"]],
            top_channels=[(int(x[0]), int(x[1])) for x in data["top_channels"]],
            ai_insight=data.get("ai_insight"),
        )

    @staticmethod
    def create_digest_embed(data: DigestData) -> Embed:
        """Create an embed for the weekly digest."""
        embed = Embed(
            title=f"Weekly Digest for {data.guild_name}",
            description="Activity summary for the past week",
            color=0x5865F2,
            timestamp=data.period_end,
        )

        # Growth section
        growth_emoji = "" if data.net_growth >= 0 else ""
        growth_text = (
            f"**{data.member_count:,}** members "
            f"({data.net_growth:+d}, {data.growth_percentage:+.1f}%)\n"
            f"+{data.members_joined} joined, -{data.members_left} left"
        )
        embed.add_field(
            name=f"{growth_emoji} Growth",
            value=growth_text,
            inline=True,
        )

        # Activity section
        msg_emoji = "" if data.message_change_pct >= 0 else ""
        activity_text = (
            f"**{data.total_messages:,}** messages ({data.message_change_pct:+.1f}%)\n"
            f"**{data.total_voice_minutes:,}** voice mins ({data.voice_change_pct:+.1f}%)\n"
            f"**{data.active_users}** active users"
        )
        embed.add_field(
            name=f"{msg_emoji} Activity",
            value=activity_text,
            inline=True,
        )

        # Top channels
        if data.top_channels:
            channels_text = "\n".join(
                f"<#{channel_id}> - {count:,} msgs"
                for channel_id, count in data.top_channels[:3]
            )
            embed.add_field(
                name="Top Channels",
                value=channels_text,
                inline=False,
            )

        # Top contributors
        if data.top_message_users:
            users_text = "\n".join(
                f"<@{user_id}> - {count:,} msgs"
                for user_id, count in data.top_message_users[:3]
            )
            embed.add_field(
                name="Top Chatters",
                value=users_text,
                inline=True,
            )

        if data.top_voice_users:
            voice_text = "\n".join(
                f"<@{user_id}> - {mins:,} mins"
                for user_id, mins in data.top_voice_users[:3]
            )
            embed.add_field(
                name="Top Voice",
                value=voice_text,
                inline=True,
            )

        # AI Insight
        if data.ai_insight:
            embed.add_field(
                name="AI Insight",
                value=data.ai_insight,
                inline=False,
            )

        embed.set_footer(text="InsightBot Weekly Digest")

        return embed
