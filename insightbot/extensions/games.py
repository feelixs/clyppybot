"""Game statistics slash commands."""

from datetime import datetime, timezone

from interactions import (
    Extension,
    slash_command,
    SlashContext,
    SlashCommandOption,
    OptionType,
    Embed,
    Member,
)

from ..logging_config import get_logger
from ..api_client import get_api_client

logger = get_logger("insightbot.extensions.games")


class GamesExtension(Extension):
    """Game statistics slash commands."""

    #@slash_command(
    #    name="topgames",
    #    description="View the most played games on this server",
    #    options=[
    #        SlashCommandOption(
    #            name="period",
    #            description="Time period (today, week, month)",
    #            type=OptionType.STRING,
    #            required=False,
    #            choices=[
    #                {"name": "Today", "value": "today"},
    #                {"name": "This Week", "value": "week"},
    #                {"name": "This Month", "value": "month"},
    #            ],
    #        ),
    #    ],
    #)
    async def topgames(self, ctx: SlashContext, period: str = "week"):
        """View the most played games on this server."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            api = get_api_client()
            games = await api.get_top_games(int(ctx.guild.id), period, limit=10)

            if not games:
                await ctx.send("No game data available yet!")
                return

            period_name = {
                "today": "Today",
                "week": "This Week",
                "month": "This Month",
            }.get(period, "This Week")

            embed = Embed(
                title=f"🎮 Top Games - {period_name}",
                description=f"Most played games in {ctx.guild.name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            for game in games[:10]:
                hours = game["total_minutes"] / 60
                avg_session_hours = game["avg_session_minutes"] / 60

                value = (
                    f"⏱️ **{hours:.1f}h** total playtime\n"
                    f"👥 **{game['unique_players']}** players\n"
                    f"🎯 **{game['session_count']}** sessions\n"
                    f"📊 **{avg_session_hours:.1f}h** avg session"
                )

                embed.add_field(
                    name=f"{game['rank']}. {game['game_name']}",
                    value=value,
                    inline=False,
                )

            embed.set_footer(text="InsightBot • Game Tracking")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting top games: {e}")
            await ctx.send("An error occurred while fetching game statistics.", ephemeral=True)

        #@slash_command(
        #name="mygames",
        #description="View your personal gaming stats",
            #options=[
            #SlashCommandOption(
            #    name="period",
            #    description="Time period (today, week, month)",
            #    type=OptionType.STRING,
            #    required=False,
            #    choices=[
            #        {"name": "Today", "value": "today"},
            #        {"name": "This Week", "value": "week"},
            #        {"name": "This Month", "value": "month"},
            #    ],
            #),
            #SlashCommandOption(
            #    name="user",
            #    description="User to view stats for (defaults to you)",
            #    type=OptionType.USER,
            #    required=False,
        #),
        #],
    #)
    async def mygames(self, ctx: SlashContext, period: str = "month", user: Member = None):
        """View your personal gaming stats."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        target_user = user or ctx.author
        is_self = target_user.id == ctx.author.id

        try:
            api = get_api_client()
            games = await api.get_user_games(int(ctx.guild.id), int(target_user.id), period)

            if not games:
                if is_self:
                    await ctx.send("You haven't played any games yet!")
                else:
                    await ctx.send(f"{target_user.mention} hasn't played any games yet!")
                return

            total_minutes = sum(g["total_minutes"] for g in games)
            total_hours = total_minutes / 60

            period_name = {
                "today": "Today",
                "week": "This Week",
                "month": "This Month",
            }.get(period, "This Month")

            title = f"🎮 {target_user.display_name}'s Games - {period_name}"
            description = f"**{total_hours:.1f}h** total across **{len(games)}** games"

            embed = Embed(
                title=title,
                description=description,
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            for idx, game in enumerate(games[:10], 1):
                hours = game["total_minutes"] / 60
                value = (
                    f"⏱️ **{hours:.1f}h** playtime\n"
                    f"🎯 **{game['session_count']}** sessions"
                )
                embed.add_field(
                    name=f"{idx}. {game['game_name']}",
                    value=value,
                    inline=False,
                )

            if len(games) > 10:
                embed.set_footer(text=f"InsightBot • Showing top 10 of {len(games)} games")
            else:
                embed.set_footer(text="InsightBot • Game Tracking")

            if target_user.avatar:
                embed.set_thumbnail(url=target_user.avatar.url)

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting user games: {e}")
            await ctx.send("An error occurred while fetching game statistics.", ephemeral=True)

        #@slash_command(
        #name="gamestats",
        #description="View overall gaming statistics for this server",
            #options=[
            #SlashCommandOption(
            #    name="period",
            #    description="Time period (today, week, month)",
            #    type=OptionType.STRING,
            #    required=False,
            #    choices=[
            #        {"name": "Today", "value": "today"},
            #        {"name": "This Week", "value": "week"},
            #        {"name": "This Month", "value": "month"},
            #    ],
        #),
        #],
    #)
    async def gamestats(self, ctx: SlashContext, period: str = "week"):
        """View overall gaming statistics for this server."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            api = get_api_client()
            stats = await api.get_server_game_stats(int(ctx.guild.id), period)

            total_hours = stats["total_minutes"] / 60

            period_name = {
                "today": "Today",
                "week": "This Week",
                "month": "This Month",
            }.get(period, "This Week")

            embed = Embed(
                title=f"📊 Server Gaming Stats - {period_name}",
                description=f"Gaming activity in {ctx.guild.name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            embed.add_field(
                name="🎮 Unique Games",
                value=f"**{stats['unique_games']}** games played",
                inline=True,
            )

            embed.add_field(
                name="👥 Active Gamers",
                value=f"**{stats['unique_players']}** players",
                inline=True,
            )

            embed.add_field(
                name="⏱️ Total Playtime",
                value=f"**{total_hours:.1f}h**",
                inline=True,
            )

            embed.add_field(
                name="🎯 Total Sessions",
                value=f"**{stats['total_sessions']}** sessions",
                inline=True,
            )

            if stats["total_sessions"] > 0:
                avg_session_hours = (stats["total_minutes"] / stats["total_sessions"]) / 60
                embed.add_field(
                    name="📊 Avg Session",
                    value=f"**{avg_session_hours:.1f}h**",
                    inline=True,
                )

            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            embed.set_footer(text="InsightBot • Game Tracking")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting game stats: {e}")
            await ctx.send("An error occurred while fetching game statistics.", ephemeral=True)
