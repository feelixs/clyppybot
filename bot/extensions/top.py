from datetime import datetime, timezone

from interactions import (
    Extension,
    slash_command,
    SlashContext,
    SlashCommandOption,
    OptionType,
    SlashCommandChoice,
    Embed
)

from ..services.stats_service import StatsService
from ..logging_config import get_logger

logger = get_logger("insightbot.extensions.top")


PERIOD_CHOICES = [
    SlashCommandChoice(name="Today", value="today"),
    SlashCommandChoice(name="This Week", value="week"),
    SlashCommandChoice(name="This Month", value="month"),
    SlashCommandChoice(name="All Time", value="year"),
]

INVITE_PERIOD_CHOICES = [
    SlashCommandChoice(name="This Week", value="week"),
    SlashCommandChoice(name="This Month", value="month"),
    SlashCommandChoice(name="All Time", value="all"),
]


class TopExtension(Extension):
    """Leaderboard slash commands."""

    @slash_command(
        name="top",
        description="View leaderboards",
        sub_cmd_name="messages",
        sub_cmd_description="View message leaderboard",
        options=[
            SlashCommandOption(
                name="period",
                description="Time period for the leaderboard",
                type=OptionType.STRING,
                required=False,
                choices=PERIOD_CHOICES,
            ),
        ],
    )
    async def top_messages(self, ctx: SlashContext, period: str = "week"):
        """Show message leaderboard."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            leaderboard = await StatsService.get_message_leaderboard(
                int(ctx.guild.id), period, 10
            )

            period_name = {
                "today": "Today",
                "week": "This Week",
                "month": "This Month",
                "year": "All Time",
            }.get(period, "This Week")

            embed = Embed(
                title=f"Message Leaderboard - {period_name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            if leaderboard:
                # Get medal emojis for top 3
                medals = ["", "", ""]

                lb_lines = []
                for entry in leaderboard:
                    medal = medals[entry.rank - 1] if entry.rank <= 3 else f"**{entry.rank}.**"
                    lb_lines.append(f"{medal} <@{entry.user_id}> - **{entry.value:,}** messages")

                embed.description = "\n".join(lb_lines)
            else:
                embed.description = "No message data available for this period."

            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            embed.set_footer(text="InsightBot")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting message leaderboard: {e}")
            await ctx.send("An error occurred while fetching the leaderboard.", ephemeral=True)

    @slash_command(
        name="top",
        description="View leaderboards",
        sub_cmd_name="voice",
        sub_cmd_description="View voice time leaderboard",
        options=[
            SlashCommandOption(
                name="period",
                description="Time period for the leaderboard",
                type=OptionType.STRING,
                required=False,
                choices=PERIOD_CHOICES,
            ),
        ],
    )
    async def top_voice(self, ctx: SlashContext, period: str = "week"):
        """Show voice time leaderboard."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            leaderboard = await StatsService.get_voice_leaderboard(
                int(ctx.guild.id), period, 10
            )

            period_name = {
                "today": "Today",
                "week": "This Week",
                "month": "This Month",
                "year": "All Time",
            }.get(period, "This Week")

            embed = Embed(
                title=f"Voice Leaderboard - {period_name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            if leaderboard:
                medals = ["", "", ""]

                lb_lines = []
                for entry in leaderboard:
                    medal = medals[entry.rank - 1] if entry.rank <= 3 else f"**{entry.rank}.**"
                    # Format time nicely
                    hours = entry.value // 60
                    minutes = entry.value % 60
                    if hours > 0:
                        time_str = f"{hours}h {minutes}m"
                    else:
                        time_str = f"{minutes}m"
                    lb_lines.append(f"{medal} <@{entry.user_id}> - **{time_str}**")

                embed.description = "\n".join(lb_lines)
            else:
                embed.description = "No voice data available for this period."

            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            embed.set_footer(text="InsightBot")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting voice leaderboard: {e}")
            await ctx.send("An error occurred while fetching the leaderboard.", ephemeral=True)

    @slash_command(
        name="top",
        description="View leaderboards",
        sub_cmd_name="games",
        sub_cmd_description="View gaming time leaderboard",
        options=[
            SlashCommandOption(
                name="period",
                description="Time period for the leaderboard",
                type=OptionType.STRING,
                required=False,
                choices=PERIOD_CHOICES,
            ),
        ],
    )
    async def top_games(self, ctx: SlashContext, period: str = "week"):
        """Show gaming time leaderboard."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            leaderboard = await StatsService.get_game_leaderboard(
                int(ctx.guild.id), period, 10
            )

            period_name = {
                "today": "Today",
                "week": "This Week",
                "month": "This Month",
                "year": "All Time",
            }.get(period, "This Week")

            embed = Embed(
                title=f"Gaming Leaderboard - {period_name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            if leaderboard:
                medals = ["", "", ""]

                lb_lines = []
                for entry in leaderboard:
                    medal = medals[entry.rank - 1] if entry.rank <= 3 else f"**{entry.rank}.**"
                    # Format time nicely
                    hours = entry.value // 60
                    minutes = entry.value % 60
                    if hours > 0:
                        time_str = f"{hours}h {minutes}m"
                    else:
                        time_str = f"{minutes}m"
                    lb_lines.append(f"{medal} <@{entry.user_id}> - **{time_str}**")

                embed.description = "\n".join(lb_lines)
            else:
                embed.description = "No gaming data available for this period."

            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            embed.set_footer(text="InsightBot")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting games leaderboard: {e}")
            await ctx.send("An error occurred while fetching the leaderboard.", ephemeral=True)

    @slash_command(
        name="top",
        description="View leaderboards",
        sub_cmd_name="invites",
        sub_cmd_description="View invite leaderboard",
        options=[
            SlashCommandOption(
                name="period",
                description="Time period for the leaderboard",
                type=OptionType.STRING,
                required=False,
                choices=INVITE_PERIOD_CHOICES,
            ),
        ],
    )
    async def top_invites(self, ctx: SlashContext, period: str = "all"):
        """Show invite leaderboard."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            leaderboard = await StatsService.get_invite_leaderboard(
                int(ctx.guild.id), period, 10
            )

            period_name = {
                "week": "This Week",
                "month": "This Month",
                "all": "All Time",
            }.get(period, "All Time")

            embed = Embed(
                title=f"Invite Leaderboard - {period_name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            if leaderboard:
                medals = ["", "", ""]

                lb_lines = []
                for entry in leaderboard:
                    medal = medals[entry.rank - 1] if entry.rank <= 3 else f"**{entry.rank}.**"
                    invite_word = "invite" if entry.value == 1 else "invites"
                    lb_lines.append(f"{medal} <@{entry.user_id}> - **{entry.value:,}** {invite_word}")

                embed.description = "\n".join(lb_lines)
            else:
                embed.description = "No invite data available for this period."

            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            embed.set_footer(text="InsightBot")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting invite leaderboard: {e}")
            await ctx.send("An error occurred while fetching the leaderboard.", ephemeral=True)


def setup(bot):
    TopExtension(bot)
