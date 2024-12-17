from interactions import Extension, Embed, slash_command, SlashContext, SlashCommandOption, OptionType, listen, \
    Permissions, ActivityType, Activity, Task, IntervalTrigger
from interactions.api.events.discord import GuildJoin, GuildLeft
from bot.tools import create_nexus_str, GuildType
import logging
import aiohttp
import os
from bot.twitch.twitchclip import TwitchClipProcessor
from bot.tools import POSSIBLE_ON_ERRORS, POSSIBLE_TOO_LARGE

VERSION = "1.3.3b"


class Base(Extension):
    def __init__(self, bot):
        self.bot = bot
        self.ready = False
        self.logger = logging.getLogger(__name__)
        self.task = Task(self.db_save_task, IntervalTrigger(seconds=60 * 30))  # save db every 30 minutes

    @slash_command(name="save", description="Save CLYPPY DB", scopes=[759798762171662399])
    async def save(self, ctx: SlashContext):
        await ctx.defer()
        await ctx.send("Saving DB...")
        await self.bot.guild_settings.save()
        await ctx.send("You can now safely exit.")

    @slash_command(name="help", description="Get help using CLYPPY")
    async def help(self, ctx: SlashContext):
        await ctx.defer()
        about = (
            "CLYPPY supports uploading Twitch clips in Full HD to your Discord channels! Send a valid Twitch Clip link to get started.\n\n"
            "**TROUBLESHOOTING**\nIf CLYPPY isn't responding to your Twitch Clip links, it could be because it has incorrect permissions for your Discord channel."
            " Required permissions are: `Attach Files`, `Send Messages`\n\n"
            "**UPDATE Dec 3rd 2024** CLYPPY is back online after a break. We are working on improving the service and adding new features. Stay tuned!")
        help_embed = Embed(title="About CLYPPY", description=about)
        help_embed.description += create_nexus_str()
        help_embed.footer = f"CLYPPY v{VERSION}"
        await ctx.send(
            content="If you only see this message, that means you have Embeds disabled. Please enable them in your Discord Settings to continue.",
            embed=help_embed)

    @slash_command(name="logs", description="Display the chatlogs for a Twitch user",
                   options=[SlashCommandOption(name="user",
                                               description="the Twitch user to check logs for",
                                               required=True,
                                               type=OptionType.STRING),
                            SlashCommandOption(name="channel",
                                               description="the Twitch channel (username) where they sent chat messages",
                                               required=True,
                                               type=OptionType.STRING),
                            SlashCommandOption(name="year",
                                               description="the year to retrieve logs from",
                                               required=False,
                                               type=OptionType.INTEGER),
                            SlashCommandOption(name="month",
                                               description="the month to retrieve logs from",
                                               required=False,
                                               type=OptionType.INTEGER)
                            ])
    async def logs(self, ctx: SlashContext, user: str, channel: str, year: int = None, month: int = None):
        try:
            async with aiohttp.ClientSession() as session:
                if year is not None and month is not None:
                    async with session.get(f"https://logs.ivr.fi/channel/{channel}/user/{user}/{year}/{month}") as resp:
                        logs_output = await resp.text()
                elif year is None and month is None:
                    async with session.get(f"https://logs.ivr.fi/channel/{channel}/user/{user}") as resp:
                        logs_output = await resp.text()
                else:
                    return await ctx.send(
                        "An error occurred: year & month must be either both filled out, or none filled out",
                        ephemeral=True)
                if logs_output.count("\n") == 0:
                    if "[" in logs_output:
                        return await ctx.send(logs_output)
                    else:
                        return await ctx.send(
                            f'for user `{user}` on Twitch channel `{channel}`:\n`' + logs_output + '`')
                else:
                    logs_output = self._get_last_lines(logs_output)
                    logs_output = self._format_log(logs_output)
                    if logs_output == "":
                        return await ctx.send(f"No logs available for `{user}` in Twitch channel `{channel}`")
                    else:
                        return await ctx.send(logs_output)
        except:
            return await ctx.send(
                "An error occurred retrieving Twitch logs, please contact out support team if the issue persists",
                ephemeral=True)

    # @slash_command(name="twitch", description="Embed a Twitch clip with chat",
    #               options=[SlashCommandOption(name="clip_url", type=OptionType.STRING,
    #                                           description="Link to the Twitch clip",
    #                                           required=True)]
    #               )
    # async def twitch(self, ctx, clip_url: str):
    #    await ctx.defer()
    #    if not self.bot.twitch.is_clip_link(clip_url):
    #        return await ctx.send(f"`{clip_url}` was not a valid twitch clip link")
    #    clip = await self.bot.twitch.get_clip(clip_url)
    #    clip_ctx = await clip.fetch_data()
    #    if not clip_ctx.video_id:
    #        return await ctx.send("Unable to retrieve the Twitch VOD from that clip")
    #    clipfile, _ = await self.bot.tools.dl.download_clip(
    #        clip=clip,
    #        guild_ctx=GuildType(ctx.guild.id, ctx.guild.name),
    #        root_msg=ctx.message,
    #        too_large_setting='trim'
    #    )
    #    try:
    #        videofile = await clip_ctx.add_chat(clipfile)
    #        await ctx.send(files=videofile)
    #    except Exception as e:
    #        return await ctx.send(f"Failed to render chat: {e}")

    @slash_command(name="setup", description="Display or change Clyppy's general settings",
                   options=[SlashCommandOption(name="error_channel", type=OptionType.CHANNEL,
                                               description="The channel where Clyppy should send error messages",
                                               required=False)])
    async def setup(self, ctx: SlashContext, error_channel=None):
        if not ctx.author.has_permission(Permissions.ADMINISTRATOR):
            await ctx.send("Only members with the **Administrator** permission can change Clyppy's settings.")
            return
        if error_channel is None:
            if (ec := self.bot.guild_settings.get_error_channel(ctx.guild.id)) == 0:
                cur_chn = ("Unconfigured\n\n"
                           "When not configured, Clyppy will send error messages to the same channel as the interaction.")
                return await ctx.send("Current error channel: " + cur_chn)
            else:
                try:
                    cur_chn = self.bot.get_channel(ec)
                    return await ctx.send(f"Current error channel: {cur_chn.mention}")
                except:
                    cur_chn = ("Channel not found - error channel was reset to **Unconfigured**\n\n"
                               "Make sure Clyppy has the `VIEW_CHANNELS` permission, and that the channel still exists."
                               "\nWhen not configured, Clyppy will send error messages to the same channel as the interaction.\n\n"
                               f"More info:\nTried to retrieve channel with id {ec} but failed.")
                    self.bot.guild_settings.set_error_channel(ctx.guild.id, 0)
                    return await ctx.send("Current error channel: " + cur_chn)

        await ctx.defer()
        if ctx.guild is None:
            await ctx.send("This command is only available in servers.")
            return
        if (e := self.bot.get_channel(error_channel)) is None:
            return await ctx.send(f"Channel #{error_channel} not found.\n\n"
                                  f"Please make sure Clyppy has the `VIEW_CHANNELS` permission & try again.")
        try:
            self.bot.guild_settings.set_error_channel(ctx.guild.id, error_channel)
            return await ctx.send(f"Success! Error channel set to {e.mention}")
        except:
            return await ctx.send("An error occurred while setting the error channel. Please try again.")

    @slash_command(name="settings", description="Display or change Clyppy's miscellaneous settings",
                   options=[SlashCommandOption(name="too_large", type=OptionType.STRING,
                                               description="Choose what CLYPPY should do with large files",
                                               required=False),
                            SlashCommandOption(name="on_error", type=OptionType.STRING,
                                               description="Choose what CLYPPY should do upon error",
                                               required=False)])
    async def settings(self, ctx: SlashContext, too_large: str = None, on_error: str = None):
        await ctx.defer()
        if ctx.guild is None:
            await ctx.send("This command is only available in servers.")
            return

        if not ctx.author.has_permission(Permissions.ADMINISTRATOR):
            await self._send_settings_help(ctx, True)
            return

        if too_large is None and on_error is None:
            await self._send_settings_help(ctx, False)
            return

        # Get current settings
        current_setting = self.bot.guild_settings.get_setting(ctx.guild.id)
        current_too_large = POSSIBLE_TOO_LARGE[int(current_setting[0])]
        current_on_error = POSSIBLE_ON_ERRORS[int(current_setting[1])]

        # Use current values if not specified
        too_large = too_large or current_too_large
        on_error = on_error or current_on_error

        if too_large not in POSSIBLE_TOO_LARGE:
            await ctx.send("Option not in the **too_large** list.")
            return

        if on_error not in POSSIBLE_ON_ERRORS:
            await ctx.send("Option not in the **on_error** list.")
            return

        too_idx = POSSIBLE_TOO_LARGE.index(too_large)
        err_idx = POSSIBLE_ON_ERRORS.index(on_error)
        await self.bot.guild_settings.set_setting(ctx.guild.id, f"{too_idx}{err_idx}")

        await ctx.send(
            "Successfully changed settings:\n\n"
            f"**too_large**: {too_large}\n"
            f"**on_error**: {on_error}"
        )

    async def _send_settings_help(self, ctx: SlashContext, prepend_admin: bool = False):
        cs = self.bot.guild_settings.get_setting_str(ctx.guild.id)
        about = (
            "**Configurable Settings:**\n"
            "Below are the settings you can configure using this command. Each setting name is in **bold**, "
            "followed by its available options.\n\n"
            "**too_large** Choose what CLYPPY should do with downloaded clips that are larger than Discord's limits of 25MB:\n"
            " - `trim`: CLYPPY will trim the video until it's within Discord's size limit and upload the resulting file.\n"
            " - `info`: CLYPPY will respond with a short statement saying he's unable to continue and the upload will fail.\n"
            " - `dm`: The upload will fail and CLYPPY will attempt to DM the author to notify them.\n"
            " - `compress`: CLYPPY will compress the file until it's within Discord's size limit and upload the resulting file (currently unavailable).\n\n"
            "**on_error** Choose what CLYPPY should do when it encounters an error while downloading a file:\n"
            " - `info`: CLYPPY responds with a statement that he can't continue.\n"
            " - `dm`: CLYPPY will attempt to DM the author to notify them of the error.\n\n"
            f"**Current Settings:**\n{cs}\n\n"
            "Something missing? Please **Suggest a Feature** using the link below."
        )

        if prepend_admin:
            about = "**ONLY MEMBERS WITH THE ADMINISTRATOR PERMISSIONS CAN EDIT SETTINGS**\n\n" + about

        tutorial_embed = Embed(title="CLYPPY SETTINGS", description=about + create_nexus_str())
        await ctx.send(embed=tutorial_embed)

    async def db_save_task(self):
        if not self.ready:
            self.logger.info("Bot not ready, skipping database save task")
            return

        await self.post_servers(len(self.bot.guilds))
        self.logger.info("Saving database to the server...")
        await self.bot.guild_settings.save()

    @listen()
    async def on_guild_join(self, event: GuildJoin):
        if self.ready:
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
            if os.getenv("TEST") is not None:
                await self.post_servers(len(self.bot.guilds))
            self.logger.info("--------------")
            await self.bot.change_presence(
                activity=Activity(type=ActivityType.STREAMING, name="/help", url="https://twitch.tv/hesmen"))

    @staticmethod
    async def post_servers(num: int):
        if os.getenv("TEST") is not None:
            return
        async with aiohttp.ClientSession() as session:
            async with session.post("https://top.gg/api/bots/1111723928604381314/stats", json={'server_count': num},
                                    headers={'Authorization': os.getenv('GG_TOKEN')}) as resp:
                await resp.json()

    @staticmethod
    def _format_log(string):
        """
        [2023-04-13 00:43:30]  hesmen: BatChest "BATCHEST" BatChest "BATCHEST" BatChest "BATCHEST" BatChest "BATCHEST" BatChest "BATCHEST" BatChest "BATCHEST"
        [2023-04-13 00:43:30]  hesmen has been timed out for 30 seconds
        [2023-04-13 00:49:33]  hesmen: BatChest "BATCHEST" BatChest "BATCHEST" BatChest "BATCHEST" BatChest "BATCHEST"
        [2023-04-13 00:49:33]  hesmen has been timed out for 30 seconds
        [2023-04-14 00:50:18]  hesmen: h
        [2023-04-14 00:50:32]  hesmen: BBoomer RAVE Fire

        becomes

        [2023-04-13 ]
        00:43:30 hesmen: BatChest "BATCHEST" BatChest "BATCHEST" BatChest "BATCHEST" BatChest "BATCHEST" BatChest "BATCHEST" BatChest "BATCHEST"
        00:43:30  hesmen has been timed out for 30 seconds
        00:49:33  hesmen: BatChest "BATCHEST" BatChest "BATCHEST" BatChest "BATCHEST" BatChest "BATCHEST"
        00:49:33 hesmen has been timed out for 30 seconds

        [2023-04-13]
        00:50:18 hesmen: h
        00:50:32 hesmen: BBoomer RAVE Fire
        """
        formatted_logs = ""
        eachdate = ""
        for ind, line in enumerate(string.split("\n")):
            if ind == 0:
                continue
            if line.strip():
                tmst, txt = line.split(" ", 1)

                if eachdate != tmst.split(" ")[0]:
                    eachdate = tmst.split(" ")[0]
                    formatted_logs += f"\n{eachdate}]\n"
                actime, txt = txt.split(']', 1)
                for c in range(len(txt)):
                    if txt[c] == "#":
                        while txt[c] != " ":
                            c += 1
                        txt = txt[:c] + "`" + txt[c:]
                        break
                formatted_logs += f"`{actime} {txt}\n"
        return formatted_logs

    @staticmethod
    def _get_last_lines(string):
        if len(string) > 2000:
            string = string[-1980:]  # the last 1980 characters
        string = string.split("\n")
        fuldate = ""
        for c in string[1]:  # this line guaranteed to not be messed up from the trim (the line[0] will be messed up)
            fuldate += c
            if c == "]":
                break
        string[0] = fuldate
        string = "\n".join(string)
        return string
