from datetime import datetime, timezone

from interactions import (
    Extension,
    slash_command,
    SlashContext,
    SlashCommandOption,
    OptionType,
    Embed,
    Member,
    GuildText
)

from ..logging_config import get_logger
from ..services.stats_service import StatsService

logger = get_logger("insightbot.extensions.stats")


class StatsExtension(Extension):
    """Stats slash commands."""

    @slash_command(
        name="stats",
        description="View server statistics",
        sub_cmd_name="server",
        sub_cmd_description="View overall server statistics",
    )
    async def stats_server(self, ctx: SlashContext):
        """Show server statistics."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            stats = await StatsService.get_server_stats(ctx.guild)

            embed = Embed(
                title=f"Server Stats: {stats.guild_name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            # Members
            growth_sign = "+" if stats.net_growth_week >= 0 else ""
            members_text = (
                f"**{stats.member_count:,}** total\n"
                f"{growth_sign}{stats.net_growth_week} this week ({stats.growth_percentage:+.1f}%)\n"
                f"+{stats.members_joined_week} joined, -{stats.members_left_week} left"
            )
            embed.add_field(name="Members", value=members_text, inline=True)

            # Boosts
            boost_text = (
                f"Level **{stats.boost_level}**\n"
                f"**{stats.boost_count}** boosts"
            )
            embed.add_field(name="Boosts", value=boost_text, inline=True)

            # Messages
            messages_text = (
                f"**{stats.messages_today:,}** today\n"
                f"**{stats.messages_week:,}** this week"
            )
            embed.add_field(name="Messages", value=messages_text, inline=True)

            # Voice
            voice_text = (
                f"**{stats.voice_minutes_today:,}** min today\n"
                f"**{stats.voice_minutes_week:,}** min this week"
            )
            embed.add_field(name="Voice", value=voice_text, inline=True)

            # Active users
            active_text = (
                f"**{stats.active_users_today}** today\n"
                f"**{stats.active_users_week}** this week"
            )
            embed.add_field(name="Active Users", value=active_text, inline=True)

            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            embed.set_footer(text="InsightBot")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting server stats: {e}")
            await ctx.send("An error occurred while fetching statistics.", ephemeral=True)

    @slash_command(
        name="stats",
        description="View server statistics",
        sub_cmd_name="channel",
        sub_cmd_description="View channel statistics",
        options=[
            SlashCommandOption(
                name="channel",
                description="The channel to view stats for (defaults to current)",
                type=OptionType.CHANNEL,
                required=False,
            ),
        ],
    )
    async def stats_channel(self, ctx: SlashContext, channel: GuildText = None):
        """Show channel statistics."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        target_channel = channel or ctx.channel

        try:
            stats = await StatsService.get_channel_stats(
                guild_id=int(ctx.guild.id),
                channel_id=int(target_channel.id),
                channel_name=target_channel.name,
            )

            embed = Embed(
                title=f"Channel Stats: #{stats.channel_name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            # Messages
            messages_text = (
                f"**{stats.messages_today:,}** today\n"
                f"**{stats.messages_week:,}** this week\n"
                f"**{stats.messages_month:,}** this month"
            )
            embed.add_field(name="Messages", value=messages_text, inline=True)

            embed.set_footer(text="InsightBot")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting channel stats: {e}")
            await ctx.send("An error occurred while fetching statistics.", ephemeral=True)

    @slash_command(
        name="stats",
        description="View server statistics",
        sub_cmd_name="user",
        sub_cmd_description="View user statistics",
        options=[
            SlashCommandOption(
                name="user",
                description="The user to view stats for (defaults to yourself)",
                type=OptionType.USER,
                required=False,
            ),
        ],
    )
    async def stats_user(self, ctx: SlashContext, user: Member = None):
        """Show user statistics."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        target_user = user or ctx.author

        try:
            stats = await StatsService.get_user_stats(
                guild_id=int(ctx.guild.id),
                user_id=int(target_user.id),
                username=target_user.username,
            )

            embed = Embed(
                title=f"Stats for {target_user.display_name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            # Messages
            msg_rank = f"#{stats.rank_messages}" if stats.rank_messages > 0 else "Unranked"
            messages_text = (
                f"**{stats.messages_today:,}** today\n"
                f"**{stats.messages_week:,}** this week\n"
                f"**{stats.messages_month:,}** this month\n"
                f"Rank: {msg_rank}"
            )
            embed.add_field(name="Messages", value=messages_text, inline=True)

            # Voice
            voice_rank = f"#{stats.rank_voice}" if stats.rank_voice > 0 else "Unranked"
            voice_text = (
                f"**{stats.voice_minutes_today:,}** min today\n"
                f"**{stats.voice_minutes_week:,}** min this week\n"
                f"**{stats.voice_minutes_month:,}** min this month\n"
                f"Rank: {voice_rank}"
            )
            embed.add_field(name="Voice", value=voice_text, inline=True)

            if target_user.avatar:
                embed.set_thumbnail(url=target_user.avatar.url)

            embed.set_footer(text="InsightBot")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            await ctx.send("An error occurred while fetching statistics.", ephemeral=True)

    @slash_command(
        name="stats",
        description="View server statistics",
        sub_cmd_name="voice",
        sub_cmd_description="View voice channel activity",
    )
    async def stats_voice(self, ctx: SlashContext):
        """Show voice channel statistics."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            stats = await StatsService.get_server_stats(ctx.guild)

            embed = Embed(
                title=f"Voice Stats: {ctx.guild.name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            voice_text = (
                f"**{stats.voice_minutes_today:,}** minutes today\n"
                f"**{stats.voice_minutes_week:,}** minutes this week"
            )
            embed.add_field(name="Total Voice Time", value=voice_text, inline=False)

            # Get voice leaderboard
            leaderboard = await StatsService.get_voice_leaderboard(
                int(ctx.guild.id), "week", 5
            )

            if leaderboard:
                lb_text = "\n".join(
                    f"**{entry.rank}.** <@{entry.user_id}> - {entry.value:,} min"
                    for entry in leaderboard
                )
                embed.add_field(name="Top Voice Users (Week)", value=lb_text, inline=False)

            embed.set_footer(text="InsightBot")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting voice stats: {e}")
            await ctx.send("An error occurred while fetching statistics.", ephemeral=True)


def setup(bot):
    StatsExtension(bot)
