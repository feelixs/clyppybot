import traceback

from interactions import Extension, Embed, slash_command, SlashContext, SlashCommandOption, OptionType, listen, Permissions
from interactions.api.events.discord import GuildJoin, GuildLeft
from bot.tools import create_nexus_str
import logging
import aiohttp
import os


VERSION = "1.1b"


class Base(Extension):
    def __init__(self, bot):
        self.bot = bot
        self.ready = False
        self.logger = logging.getLogger(__name__)

    @slash_command(name="help", description="Get help using CLYPPY")
    async def help(self, ctx: SlashContext):
        about = (
            "CLYPPY supports uploading Twitch clips in Full HD to your Discord channels! Send a valid Twitch Clip link to get started.\n\n"
            "**TROUBLESHOOTING**\nIf CLYPPY isn't responding to your Twitch Clip links, it could be because it has incorrect permissions for your Discord channel."
            " Required permissions are: `Attach Files`, `Send Messages`\n\n"
            "**UPDATE Dec 3rd 2024** CLYPPY is back online after a break. We are working on improving the service and adding new features. Stay tuned!")
        help_embed = Embed(title="About CLYPPY", description=about)
        help_embed.description += create_nexus_str()
        help_embed.footer = f"CLYPPY v{VERSION}"
        await ctx.send(embed=help_embed)

    @slash_command(name="settings", description="Display or change CLYPPY's settings",
                   options=[SlashCommandOption(name="too_large", type=OptionType.STRING,
                                               description="Choose what CLYPPY should do with large files",
                                               required=False),
                            SlashCommandOption(name="on_error", type=OptionType.STRING,
                                               description="Choose what CLYPPY should do upon error",
                                               required=False)])
    async def settings(self, ctx: SlashContext, too_large: str = None, on_error: str = None):
        prepend_admin = False

        possible_can_edits = ["trim", "info", "none"]
        possible_on_errors = ["info", "none"]
        can_edit = False
        if too_large in possible_can_edits:
            can_edit = True
        if on_error in possible_on_errors:
            can_edit = True
        if not ctx.author.has_permission(Permissions.ADMINISTRATOR):
            can_edit = False
            prepend_admin = True

        if not can_edit:
            # respond with tutorial
            cs = self.bot.guild_settings.get_setting_str(ctx.guild.id)
            self.logger.info(self.bot.guild_settings.get_setting(ctx.guild.id))
            about = ("**Configurable Settings:**\n"
                     "Below are the settings you can configure using this command. Each setting name is in **bold**, "
                     "followed by its available options.\n\n"
                     "**too_large** Choose what CLYPPY should do with downloaded clips that are larger than Discord's limits of 25MB:\n"
                     " - `trim`: CLYPPY will trim the video until it's within Discord's size limit and upload the resulting file.\n"
                     " - `info`: CLYPPY will respond with a short statement saying he's unable to continue and the upload will fail.\n"
                     " - `none`: The upload will fail and CLYPPY will do nothing.\n"
                     " - `compress`: CLYPPY will compress the file until it's within Discord's size limit and upload the resulting file (currently unavailable).\n\n"
                     "**on_error** Choose what CLYPPY should do when it encounters an error while downloading a file:\n"
                     " - `info`: CLYPPY responds with a statement that he can't continue.\n"
                     " - `none`: CLYPPY will do nothing\n\n"
                     f"**Current Settings**\n{cs}\n"
                     "Something missing? Please **Suggest a feature** using the link below.")
            if prepend_admin:
                about = "**ONLY MEMBERS WITH THE ADMINISTRATOR PERMISSIONS CAN EDIT SETTINGS**\n\n" + about
            tutorial_embed = Embed(title="CLYPPY SETTINGS", description=about + create_nexus_str())
            await ctx.send(embed=tutorial_embed)
        else:
            try:
                if too_large is None:
                    too_large = possible_on_errors[0]
                possible_can_edits = possible_can_edits.index(too_large)
            except ValueError:
                self.logger.error(traceback.format_exc())
                await ctx.send("Option not in the **too_large** list.")
            try:
                if on_error is None:
                    on_error = possible_on_errors[0]
                possible_on_errors = possible_on_errors.index(on_error)
            except ValueError:
                self.logger.error(traceback.format_exc())
                await ctx.send("Option not in the **on_error** list.")
            # results in "00", "12", etc
            self.bot.guild_settings.set_setting(ctx.guild.id, str(possible_can_edits) + str(possible_on_errors))
            await ctx.send("Successfully changed settings:\n\n"
                           f"**too_large**: {too_large}\n"
                           f"**on_error**: {on_error}")

    @listen()
    async def on_guild_join(self, event: GuildJoin):
        if self.ready:
            if os.getenv("TEST") is not None:
                await self.post_servers(len(self.bot.guilds))
            self.logger.info(f'Joined new guild: {event.guild.name}')

    @listen()
    async def on_guild_left(self, event: GuildLeft):
        if self.ready:
            self.logger.info(f'Left guild: {event.guild.name}')
            await self.post_servers(len(self.bot.guilds))

    @listen()
    async def on_ready(self):
        if not self.ready:
            self.ready = True
            self.logger.info(f"bot logged in as {self.bot.user.username}")
            self.logger.info(f"total shards: {len(self.bot.shards)}")
            self.logger.info(f"my guilds: {len(self.bot.guilds)}")
            self.logger.info(f"CLYPPY Version: {VERSION}")
            self.logger.info("--------------")

    @staticmethod
    async def post_servers(num: int):
        async with aiohttp.ClientSession() as session:
            async with session.post("https://top.gg/api/bots/1111723928604381314/stats", json={'server_count': num},
                                    headers={'Authorization': os.getenv('GG_TOKEN')}) as resp:
                await resp.json()
