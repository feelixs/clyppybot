import re
from datetime import datetime, timezone

from interactions import (
    Extension,
    slash_command,
    SlashContext,
    SlashCommandOption,
    OptionType,
    ChannelType,
    Embed,
    GuildVoice,
    Role,
    Permissions,
    check,
    Button,
    ButtonStyle,
    ActionRow,
    component_callback,
    ComponentContext,
)

from ..services.counter_service import CounterService
from ..api_client import get_api_client
from ..logging_config import get_logger

logger = get_logger("insightbot.extensions.counters")


VALID_KEYWORDS = {"members", "online", "voice", "boosts", "role", "goal"}
KEYWORD_LIMITS = {0: 1, 1: 2, 2: None}  # None = unlimited


def extract_keywords(template: str) -> set[str]:
    """Extract keyword names from template."""
    return set(re.findall(r'\{(\w+)}', template))


def has_manage_channels():
    """Check if user has Manage Channels permission."""
    async def predicate(ctx: SlashContext) -> bool:
        if not ctx.author.guild_permissions:
            return False
        return Permissions.MANAGE_CHANNELS in ctx.author.guild_permissions
    return check(predicate)


class CountersExtension(Extension):
    """Counter channel commands."""

    def __init__(self, bot):
        self.bot = bot
        self._pending_overwrites: dict[int, dict] = {}  # channel_id -> counter data

        #@slash_command(
        #name="counter",
        #description="Manage counter channels",
        #sub_cmd_name="setup",
        #sub_cmd_description="Create a counter channel",
        #options=[
        #    SlashCommandOption(
        #        name="channel",
        #        description="The voice channel to use as counter",
        #        type=OptionType.CHANNEL,
        #        channel_types=[ChannelType.GUILD_VOICE],
        #        required=True,
        #    ),
        #    SlashCommandOption(
        #        name="template",
        #        description="Text to display. Use /counter help for available keywords.",
        #        type=OptionType.STRING,
        #        required=True,
        #    ),
        #    SlashCommandOption(
        #        name="role",
        #        description="Role to count (for {role} keyword)",
        #        type=OptionType.ROLE,
        #        required=False,
        #    ),
        #    SlashCommandOption(
        #        name="goal",
        #        description="Goal target number (for {goal} keyword)",
        #        type=OptionType.INTEGER,
        #        required=False,
        #    ),
        #],
    #)
    @has_manage_channels()
    async def counter_setup(
        self,
        ctx: SlashContext,
        channel: GuildVoice,
        template: str,
        role: Role = None,
        goal: int = None,
    ):
        """Set up a counter channel."""
        await ctx.defer(ephemeral=True)

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        # Extract and validate keywords
        keywords = extract_keywords(template)

        if not keywords:
            await ctx.send(
                "Template must include at least one keyword like `{members}`. "
                "Use `/counter help` for available keywords.",
                ephemeral=True,
            )
            return

        # Check for unknown keywords
        unknown = keywords - VALID_KEYWORDS
        if unknown:
            await ctx.send(
                f"Unknown keywords: {', '.join(f'{{{k}}}' for k in unknown)}. "
                "Use `/counter help` for available keywords.",
                ephemeral=True,
            )
            return

        # Validate {role} requires role option
        if "role" in keywords and role is None:
            await ctx.send(
                "The `{role}` keyword requires selecting a role.",
                ephemeral=True,
            )
            return

        # Validate {goal} requires goal option
        if "goal" in keywords and goal is None:
            await ctx.send(
                "The `{goal}` keyword requires setting a goal number.",
                ephemeral=True,
            )
            return

        # Check tier-based keyword limit
        api = get_api_client()
        tier = await api.get_tier(int(ctx.guild.id))
        limit = KEYWORD_LIMITS.get(tier, 1)

        if limit is not None and len(keywords) > limit:
            await ctx.send(
                f"Your tier allows {limit} keyword(s) per counter. "
                f"You used {len(keywords)}: {', '.join(f'{{{k}}}' for k in keywords)}. "
                "Upgrade to use more keywords.",
                ephemeral=True,
            )
            return

        # Check tier-based counter limit
        try:
            api = get_api_client()
            limit_check = await api.can_create_counter(int(ctx.guild.id))

            if not limit_check["allowed"]:
                limit = limit_check["limit"]
                current = limit_check["current"]
                await ctx.send(
                    f"Counter limit reached ({current}/{limit}). "
                    "Upgrade your subscription to create more counters.",
                    ephemeral=True,
                )
                return
        except Exception as e:
            logger.error(f"Error checking counter limit: {e}")
            # Continue anyway if check fails

        try:
            counter = await CounterService.create_counter(
                guild=ctx.guild,
                channel=channel,
                template=template,
                role_id=int(role.id) if role else None,
                goal_target=goal,
            )

            keywords_used = ", ".join(f"{{{k}}}" for k in keywords)
            embed = Embed(
                title="Counter Created",
                description=f"Successfully created a counter in {channel.mention}",
                color=0x57F287,
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="Template", value=f"`{template}`", inline=True)
            embed.add_field(name="Keywords", value=keywords_used, inline=True)

            await ctx.send(embed=embed, ephemeral=True)

        except ValueError as e:
            if "already has a counter" in str(e):
                # Store pending data and ask for confirmation
                self._pending_overwrites[int(channel.id)] = {
                    "guild": ctx.guild,
                    "channel": channel,
                    "template": template,
                    "role_id": int(role.id) if role else None,
                    "goal_target": goal,
                }

                buttons = ActionRow(
                    Button(style=ButtonStyle.GREEN, label="Yes", custom_id=f"counter_overwrite_yes_{channel.id}"),
                    Button(style=ButtonStyle.RED, label="No", custom_id=f"counter_overwrite_no_{channel.id}"),
                )

                await ctx.send(
                    f"This channel already has a counter configured. Would you like to overwrite it?",
                    components=[buttons],
                    ephemeral=True,
                )
            else:
                await ctx.send(str(e), ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating counter: {e}")
            await ctx.send("An error occurred while creating the counter.", ephemeral=True)

        #@slash_command(
        #name="counter",
        #description="Manage counter channels",
        #sub_cmd_name="remove",
        #sub_cmd_description="Remove a counter channel",
            #options=[
            #SlashCommandOption(
            #    name="channel",
            #    description="The counter channel to remove",
            #    type=OptionType.CHANNEL,
            #    channel_types=[ChannelType.GUILD_VOICE],
            #    required=True,
        #),
        #],
    #)
    @has_manage_channels()
    async def counter_remove(self, ctx: SlashContext, channel: GuildVoice):
        """Remove a counter channel."""
        await ctx.defer(ephemeral=True)

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            removed = await CounterService.remove_counter(int(channel.id))

            if removed:
                await ctx.send(
                    f"Counter removed from {channel.mention}. "
                    "You may want to rename or delete the channel.",
                    ephemeral=True,
                )
            else:
                await ctx.send(
                    "That channel doesn't have a counter configured.",
                    ephemeral=True,
                )

        except Exception as e:
            logger.error(f"Error removing counter: {e}")
            await ctx.send("An error occurred while removing the counter.", ephemeral=True)

        #@slash_command(
        #name="counter",
        #description="Manage counter channels",
        #sub_cmd_name="help",
        #sub_cmd_description="Learn how to create counter channels",
    #)
    async def counter_help(self, ctx: SlashContext):
        """Show help for counter keywords."""
        embed = Embed(
            title="Counter Keywords",
            description="Use these keywords in your template:",
            color=0x5865F2,
        )
        embed.add_field(
            name="Available Keywords",
            value=(
                "`{members}` - Total server members\n"
                "`{online}` - Online members\n"
                "`{voice}` - Members in voice\n"
                "`{boosts}` - Server boosts\n"
                "`{role}` - Members with role (requires role option)\n"
                "`{goal}` - Goal target (requires goal option)"
            ),
            inline=False,
        )
        embed.add_field(
            name="Examples",
            value=(
                "`Members: {members}`\n"
                "`{online} online / {members} total`\n"
                "`{role} verified members`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Keyword Limits",
            value=(
                "Free: 1 keyword per counter\n"
                "Tier 1: 2 keywords per counter\n"
                "Tier 2: Unlimited"
            ),
            inline=True,
        )
        embed.add_field(
            name="Server Counter Limits",
            value=(
                "Free: 3 counters\n"
                "Tier 1: 5 counters\n"
                "Tier 2: Unlimited"
            ),
            inline=True,
        )
        await ctx.send(embed=embed, ephemeral=True)

        #@slash_command(
        #name="counter",
        #description="Manage counter channels",
        #sub_cmd_name="list",
        #sub_cmd_description="List all counter channels",
    #)
    async def counter_list(self, ctx: SlashContext):
        """List all counter channels."""
        await ctx.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            counters = await CounterService.get_guild_counters(int(ctx.guild.id))

            # Get limit info
            api = get_api_client()
            limit_info = await api.can_create_counter(int(ctx.guild.id))
            current = limit_info["current"]
            limit = limit_info["limit"]
            limit_text = f"{current}/{limit}" if limit else f"{current} (unlimited)"

            embed = Embed(
                title="Counter Channels",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )

            if counters:
                for counter in counters:
                    keywords = extract_keywords(counter.template)
                    keywords_str = ", ".join(f"{{{k}}}" for k in keywords) if keywords else "N/A"
                    value = f"Template: `{counter.template}`\n"
                    value += f"Keywords: {keywords_str}"
                    if counter.role_id:
                        value += f"\nRole: <@&{counter.role_id}>"
                    if counter.goal_target:
                        value += f"\nGoal: {counter.goal_target:,}"

                    embed.add_field(
                        name=f"<#{counter.channel_id}>",
                        value=value,
                        inline=True,
                    )
            else:
                embed.description = "No counter channels configured.\n\nUse `/counter setup` to create one."

            embed.set_footer(text=f"Counters: {limit_text}")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error listing counters: {e}")
            await ctx.send("An error occurred while fetching counters.", ephemeral=True)

    @component_callback(re.compile(r"counter_overwrite_yes_\d+"))
    async def on_overwrite_yes(self, ctx: ComponentContext):
        """Handle counter overwrite confirmation."""
        # Extract channel_id from custom_id
        channel_id = int(ctx.custom_id.replace("counter_overwrite_yes_", ""))

        pending = self._pending_overwrites.pop(channel_id, None)
        if not pending:
            await ctx.send("This confirmation has expired. Please run the command again.", ephemeral=True)
            return

        try:
            # Remove old counter first
            await CounterService.remove_counter(channel_id)

            # Create new counter
            counter = await CounterService.create_counter(
                guild=pending["guild"],
                channel=pending["channel"],
                template=pending["template"],
                role_id=pending["role_id"],
                goal_target=pending["goal_target"],
            )

            keywords = extract_keywords(pending["template"])
            keywords_used = ", ".join(f"{{{k}}}" for k in keywords)
            embed = Embed(
                title="Counter Overwritten",
                description=f"Successfully created a counter in <#{channel_id}>",
                color=0x57F287,
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="Template", value=f"`{pending['template']}`", inline=True)
            embed.add_field(name="Keywords", value=keywords_used, inline=True)

            await ctx.edit_origin(content=None, embed=embed, components=[])

        except Exception as e:
            logger.error(f"Error overwriting counter: {e}")
            await ctx.edit_origin(content="An error occurred while overwriting the counter.", components=[])

    @component_callback(re.compile(r"counter_overwrite_no_\d+"))
    async def on_overwrite_no(self, ctx: ComponentContext):
        """Handle counter overwrite cancellation."""
        channel_id = int(ctx.custom_id.replace("counter_overwrite_no_", ""))
        self._pending_overwrites.pop(channel_id, None)
        await ctx.edit_origin(content="Counter setup cancelled.", components=[])


def setup(bot):
    CountersExtension(bot)
