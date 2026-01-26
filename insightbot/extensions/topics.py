"""Topic tracking slash commands."""

from datetime import datetime, timezone

from interactions import (
    Extension,
    slash_command,
    SlashContext,
    SlashCommandOption,
    OptionType,
    SlashCommandChoice,
    Embed,
    GuildText,
)

from ..logging_config import get_logger
from ..api_client import get_api_client

logger = get_logger("insightbot.extensions.topics")

PERIOD_CHOICES = [
    SlashCommandChoice(name="Today", value="1"),
    SlashCommandChoice(name="This Week", value="7"),
    SlashCommandChoice(name="This Month", value="30"),
]


class TopicsExtension(Extension):
    """Topic tracking slash commands."""

    #@slash_command(
    #    name="topics",
    #    description="View topic insights",
    #    sub_cmd_name="trending",
    #    sub_cmd_description="View trending topics in this server",
    #    options=[
    #        SlashCommandOption(
    #            name="period",
    #            description="Time period to analyze",
    #            type=OptionType.STRING,
    #            required=False,
    #            choices=PERIOD_CHOICES,
    #        ),
    #        SlashCommandOption(
    #            name="limit",
    #            description="Number of topics to show (5-20)",
    #            type=OptionType.INTEGER,
    #            required=False,
    #            min_value=5,
    #            max_value=20,
    #        ),
    #    ],
    #)
    async def topics_trending(self, ctx: SlashContext, period: str = "7", limit: int = 10):
        """View trending topics in this server."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            api = get_api_client()
            days = int(period)
            result = await api.get_trending_topics(int(ctx.guild.id), days, limit)

            period_name = {
                "1": "Today",
                "7": "This Week",
                "30": "This Month",
            }.get(period, "This Week")

            embed = Embed(
                title=f"Trending Topics - {period_name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            topics = result.get("topics", [])
            if topics:
                medals = ["\U0001f947", "\U0001f948", "\U0001f949"]

                lines = []
                for i, topic in enumerate(topics):
                    rank = i + 1
                    medal = medals[rank - 1] if rank <= 3 else f"**{rank}.**"
                    name = topic["name"]
                    mentions = topic["mentions"]
                    users = topic["unique_users"]
                    lines.append(f"{medal} {name} - **{mentions:,}** mentions ({users} users)")

                embed.description = "\n".join(lines)
            else:
                embed.description = "No topic data available for this period."

            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            embed.set_footer(text="InsightBot")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting trending topics: {e}")
            await ctx.send("An error occurred while fetching trending topics.", ephemeral=True)

        #@slash_command(
        #name="topics",
        #description="View topic insights",
        #sub_cmd_name="channel",
        #sub_cmd_description="View trending topics in a specific channel",
            #options=[
            #SlashCommandOption(
            #    name="channel",
            #    description="Channel to analyze",
            #    type=OptionType.CHANNEL,
            #    required=True,
            #),
            #SlashCommandOption(
            #    name="period",
            #    description="Time period to analyze",
            #    type=OptionType.STRING,
            #    required=False,
            #    choices=PERIOD_CHOICES,
            #),
            #SlashCommandOption(
            #    name="limit",
            #    description="Number of topics to show (5-20)",
            #    type=OptionType.INTEGER,
            #    required=False,
            #    min_value=5,
            #    max_value=20,
        #),
        #],
    #)
    async def topics_channel(self, ctx: SlashContext, channel: GuildText, period: str = "7", limit: int = 10):
        """View trending topics in a specific channel."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            api = get_api_client()
            days = int(period)
            result = await api.get_channel_topics(int(ctx.guild.id), int(channel.id), days, limit)

            period_name = {
                "1": "Today",
                "7": "This Week",
                "30": "This Month",
            }.get(period, "This Week")

            embed = Embed(
                title=f"Channel Topics: {channel.mention} - {period_name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            topics = result.get("topics", [])
            if topics:
                medals = ["\U0001f947", "\U0001f948", "\U0001f949"]

                lines = []
                for i, topic in enumerate(topics):
                    rank = i + 1
                    medal = medals[rank - 1] if rank <= 3 else f"**{rank}.**"
                    name = topic["name"]
                    mentions = topic["mentions"]
                    users = topic["unique_users"]
                    lines.append(f"{medal} {name} - **{mentions:,}** mentions ({users} users)")

                embed.description = "\n".join(lines)
            else:
                embed.description = "No topic data available for this channel."

            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            embed.set_footer(text="InsightBot")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting channel topics: {e}")
            await ctx.send("An error occurred while fetching channel topics.", ephemeral=True)

        #@slash_command(
        #name="topics",
        #description="View topic insights",
        #sub_cmd_name="emerging",
        #sub_cmd_description="View potential new topics from unknown words",
            #options=[
            #SlashCommandOption(
            #    name="min_users",
            #    description="Minimum unique users mentioning the word",
            #    type=OptionType.INTEGER,
            #    required=False,
            #    min_value=1,
            #    max_value=50,
            #),
            #SlashCommandOption(
            #    name="limit",
            #    description="Number of words to show (5-20)",
            #    type=OptionType.INTEGER,
            #    required=False,
            #    min_value=5,
            #    max_value=20,
        #),
        #],
    #)
    async def topics_emerging(self, ctx: SlashContext, min_users: int = 3, limit: int = 10):
        """View potential new topics from unknown words."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            api = get_api_client()
            result = await api.get_emerging_topics(int(ctx.guild.id), min_users, limit)

            embed = Embed(
                title="Emerging Topics",
                description=f"Potential new topics in {ctx.guild.name}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            words = result.get("words", [])
            if words:
                medals = ["\U0001f947", "\U0001f948", "\U0001f949"]

                lines = []
                for i, word_data in enumerate(words):
                    rank = i + 1
                    medal = medals[rank - 1] if rank <= 3 else f"**{rank}.**"
                    word = word_data["word"]
                    mentions = word_data["mentions"]
                    users = word_data["unique_users"]
                    lines.append(f'{medal} "{word}" - **{mentions:,}** mentions ({users} users)')

                embed.description = "\n".join(lines)
            else:
                embed.description = "No emerging topics found. Try lowering the minimum users threshold."

            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            embed.set_footer(text="InsightBot")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting emerging topics: {e}")
            await ctx.send("An error occurred while fetching emerging topics.", ephemeral=True)

        #@slash_command(
        #name="topics",
        #description="View topic insights",
        #sub_cmd_name="stats",
        #sub_cmd_description="View overall topic statistics for this server",
    #)
    async def topics_stats(self, ctx: SlashContext):
        """View overall topic statistics."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            api = get_api_client()
            result = await api.get_topic_stats(int(ctx.guild.id))

            embed = Embed(
                title="Topic Statistics",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            unique_topics = result.get("unique_topics", 0)
            total_mentions = result.get("total_mentions", 0)
            top_category = result.get("top_category")
            unknown_count = result.get("unknown_words_count", 0)
            categories = result.get("categories", [])

            # Tracking summary
            summary_lines = [
                f"\u2022 **{unique_topics:,}** unique topics tracked",
                f"\u2022 **{total_mentions:,}** total mentions",
            ]
            if top_category:
                summary_lines.append(f"\u2022 Top category: **{top_category}**")

            embed.add_field(
                name="\U0001f4ca Tracking Summary",
                value="\n".join(summary_lines),
                inline=False,
            )

            # Category breakdown
            if categories:
                cat_lines = []
                for i, cat in enumerate(categories):
                    name = cat["name"]
                    mentions = cat["mentions"]
                    if total_mentions > 0:
                        pct = (mentions / total_mentions) * 100
                        cat_lines.append(f"**{i + 1}.** {name} - {mentions:,} ({pct:.0f}%)")
                    else:
                        cat_lines.append(f"**{i + 1}.** {name} - {mentions:,}")

                embed.add_field(
                    name="\U0001f4c1 Top Categories",
                    value="\n".join(cat_lines),
                    inline=False,
                )

            # Unknown words
            embed.add_field(
                name="\U0001f50d Unknown Words",
                value=f"**{unknown_count:,}** potential new topics",
                inline=False,
            )

            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            embed.set_footer(text="InsightBot")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting topic stats: {e}")
            await ctx.send("An error occurred while fetching topic statistics.", ephemeral=True)


def setup(bot):
    TopicsExtension(bot)
