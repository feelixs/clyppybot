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
    Permissions,
    check,
)

from ..logging_config import get_logger
from ..api_client import get_api_client
from ..services.digest_service import DigestService

logger = get_logger("insightbot.extensions.admin")


DAY_CHOICES = [
    SlashCommandChoice(name="Monday", value=0),
    SlashCommandChoice(name="Tuesday", value=1),
    SlashCommandChoice(name="Wednesday", value=2),
    SlashCommandChoice(name="Thursday", value=3),
    SlashCommandChoice(name="Friday", value=4),
    SlashCommandChoice(name="Saturday", value=5),
    SlashCommandChoice(name="Sunday", value=6),
]


def has_manage_guild():
    """Check if user has Manage Server permission."""
    async def predicate(ctx: SlashContext) -> bool:
        if not ctx.author.guild_permissions:
            return False
        return Permissions.MANAGE_GUILD in ctx.author.guild_permissions
    return check(predicate)


class AdminExtension(Extension):
    """Admin and digest commands."""

    @slash_command(
        name="digest",
        description="Manage weekly digests",
        sub_cmd_name="setup",
        sub_cmd_description="Configure weekly digest",
        options=[
            SlashCommandOption(
                name="channel",
                description="Channel to post digests in",
                type=OptionType.CHANNEL,
                required=True,
            ),
            SlashCommandOption(
                name="day",
                description="Day of the week to post",
                type=OptionType.INTEGER,
                required=False,
                choices=DAY_CHOICES,
            ),
            SlashCommandOption(
                name="hour",
                description="Hour to post (UTC, 0-23)",
                type=OptionType.INTEGER,
                required=False,
                min_value=0,
                max_value=23,
            ),
        ],
    )
    @has_manage_guild()
    async def digest_setup(
        self,
        ctx: SlashContext,
        channel: GuildText,
        day: int = 0,
        hour: int = 12,
    ):
        """Set up weekly digest."""
        await ctx.defer(ephemeral=True)

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            await DigestService.configure_digest(
                guild_id=int(ctx.guild.id),
                channel_id=int(channel.id),
                day_of_week=day,
                hour_utc=hour,
            )

            day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][day]

            embed = Embed(
                title="Digest Configured",
                description=f"Weekly digest will be posted in {channel.mention}",
                color=0x57F287,
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="Day", value=day_name, inline=True)
            embed.add_field(name="Time", value=f"{hour:02d}:00 UTC", inline=True)

            await ctx.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting up digest: {e}")
            await ctx.send("An error occurred while configuring the digest.", ephemeral=True)

    @slash_command(
        name="digest",
        description="Manage weekly digests",
        sub_cmd_name="disable",
        sub_cmd_description="Disable weekly digest",
    )
    @has_manage_guild()
    async def digest_disable(self, ctx: SlashContext):
        """Disable weekly digest."""
        await ctx.defer(ephemeral=True)

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            await DigestService.disable_digest(int(ctx.guild.id))
            await ctx.send("Weekly digest has been disabled.", ephemeral=True)

        except Exception as e:
            logger.error(f"Error disabling digest: {e}")
            await ctx.send("An error occurred while disabling the digest.", ephemeral=True)

    @slash_command(
        name="digest",
        description="Manage weekly digests",
        sub_cmd_name="preview",
        sub_cmd_description="Preview the current week's digest",
    )
    @has_manage_guild()
    async def digest_preview(self, ctx: SlashContext):
        """Preview the weekly digest."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            api = get_api_client()

            # Check and consume preview (handles tier internally)
            result = await api.use_preview(int(ctx.guild.id))

            if not result["allowed"]:
                await ctx.send(
                    f"Preview limit reached ({result['limit']}/week). Resets <t:{result['resets_at']}:R>.",
                    ephemeral=True,
                )
                return

            # Generate digest data
            data = await DigestService.get_digest_data(ctx.guild)

            # Create the embed
            embed = DigestService.create_digest_embed(data)

            # Add preview notice
            embed.title = f"[PREVIEW] {embed.title}"
            embed.color = 0xFEE75C  # Yellow for preview
            embed.set_footer(text=f"Previews remaining this week: {result['remaining']}/{result['limit']}")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error generating digest preview: {e}")
            await ctx.send("An error occurred while generating the digest preview.", ephemeral=True)

    @slash_command(
        name="digest",
        description="Manage weekly digests",
        sub_cmd_name="status",
        sub_cmd_description="Check digest configuration status",
    )
    async def digest_status(self, ctx: SlashContext):
        """Check digest status."""
        await ctx.defer(ephemeral=True)

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            api = get_api_client()
            config = await api.get_digest_config(int(ctx.guild.id))

            if not config:
                await ctx.send(
                    "Weekly digest is not configured.\n"
                    "Use `/digest setup` to configure it.",
                    ephemeral=True,
                )
                return

            day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][
                config["day_of_week"]
            ]

            embed = Embed(
                title="Digest Status",
                color=0x57F287 if config["enabled"] else 0xED4245,
                timestamp=datetime.now(timezone.utc),
            )

            embed.add_field(
                name="Status",
                value="Enabled" if config["enabled"] else "Disabled",
                inline=True,
            )
            embed.add_field(name="Channel", value=f"<#{config['channel_id']}>", inline=True)
            embed.add_field(name="Schedule", value=f"{day_name} at {config['hour_utc']:02d}:00 UTC", inline=True)

            last_sent = config.get("last_sent_at")
            if last_sent:
                if isinstance(last_sent, str):
                    from datetime import datetime as dt
                    last_sent = dt.fromisoformat(last_sent.replace("Z", "+00:00"))
                embed.add_field(
                    name="Last Sent",
                    value=f"<t:{int(last_sent.timestamp())}:R>",
                    inline=True,
                )

            await ctx.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error checking digest status: {e}")
            await ctx.send("An error occurred while checking digest status.", ephemeral=True)


def setup(bot):
    AdminExtension(bot)
