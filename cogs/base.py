import asyncio
from interactions import Extension, Embed, slash_command, SlashContext, SlashCommandOption, OptionType, listen, \
    Permissions, ActivityType, Activity, Task, IntervalTrigger
from interactions.api.events.discord import GuildJoin, GuildLeft
from bot.tools import create_nexus_str, GuildType
import logging
import aiohttp
import os
from bot.tools import AutoEmbedder
from bot.tools import POSSIBLE_ON_ERRORS, POSSIBLE_EMBED_BUTTONS
from bot.tools.misc import SUPPORT_SERVER_URL, TOPGG_VOTE_LINK, INFINITY_VOTE_LINK, DLIST_VOTE_LINK, BOTLISTME_VOTE_LINK
from typing import Tuple, Optional
from bot.classes import BaseMisc, MAX_VIDEO_LEN_SEC, VideoTooLong, NoDuration, ClipFailure
import re
import time


LOGGER_WEBHOOK = os.getenv('LOG_WEBHOOK')

VERSION = "1.5.1b"


def compute_platform(url: str, bot) -> Tuple[Optional[BaseMisc], Optional[str]]:
    """Determine the platform and clip ID from the URL"""
    # Medal.tv patterns
    medal_patterns = [
        r'^https?://(?:www\.)?medal\.tv/games/[\w-]+/clips/([\w-]+)',
        r'^https?://(?:www\.)?medal\.tv/clips/([\w-]+)'
    ]
    for pattern in medal_patterns:
        if match := re.match(pattern, url):
            return bot.medal, match.group(1)

    # Kick.com pattern
    kick_pattern = r'^https?://(?:www\.)?kick\.com/[\w-]+(?:/clips/|/\?clip=)(?:clip_)?([\w-]+)'
    if match := re.match(kick_pattern, url):
        return bot.kick, match.group(1)

    # Twitch patterns
    twitch_patterns = [
        r'https?://(?:www\.|m\.)?clips\.twitch\.tv/([\w-]+)',
        r'https?://(?:www\.|m\.)?twitch\.tv/(?:[a-zA-Z0-9_-]+/)?clip/([\w-]+)',
        r'https?://(?:www\.)?clyppy\.com/?clips/([a-zA-Z0-9_-]+)',
        r'https?://(?:www\.)?clyppy\.io/?clips/([a-zA-Z0-9_-]+)'
    ]
    for pattern in twitch_patterns:
        if match := re.match(pattern, url):
            return bot.twitch, match.group(1)

    xpatterns = [
        r'(?:https?://)?(?:www\.)?twitter\.com/\w+/status/(\d+)',
        r'(?:https?://)?(?:www\.)?fxtwitter\.com/\w+/status/(\d+)',
        r'(?:https?://)?(?:www\.)?fixupx\.com/\w+/status/(\d+)',
        r'(?:https?://)?(?:www\.)?x\.com/\w+/status/(\d+)',
    ]
    for pattern in xpatterns:
        if match := re.match(pattern, url):
            return bot.x, match.group(1)

    ytpatterns = [
        r'^(?:https?://)?(?:(?:www|m)\.)?(?:youtube\.com/(?:[^/]+/.+/|(?:v|e(?:mbed)?)/|.*[?&]v=)|youtu\.be/)([^"&?/ ]{11})',
        r'^(?:https?://)?(?:(?:www|m)\.)?(?:youtube\.com/shorts/)([^"&?/ ]{11})',
        r'^(?:https?://)?(?:(?:www|m)\.)?youtube\.com/clip/([^"&?/ ]{11})'
    ]
    for pattern in ytpatterns:
        if match := re.match(pattern, url):
            return bot.yt, match.group(1)

    reddit_patterns = [
        r'(?:https?://)?(?:www\.)?reddit\.com/r/[^/]+/comments/([a-zA-Z0-9]+)',  # Standard format
        r'(?:https?://)?(?:www\.)?redd\.it/([a-zA-Z0-9]+)',  # Short links
        r'(?:https?://)?(?:www\.)?reddit\.com/gallery/([a-zA-Z0-9]+)',  # Gallery links
        r'(?:https?://)?(?:www\.)?reddit\.com/user/[^/]+/comments/([a-zA-Z0-9]+)',  # User posts
        r'(?:https?://)?(?:www\.)?reddit\.com/r/[^/]+/duplicates/([a-zA-Z0-9]+)',  # Crossposts
        r'(?:https?://)?(?:www\.)?reddit\.com/r/[^/]+/s/([a-zA-Z0-9]+)',  # Share links
        r'(?:https?://)?v\.redd\.it/([a-zA-Z0-9]+)'  # Video links
    ]
    for pattern in reddit_patterns:
        if match := re.match(pattern, url):
            return bot.reddit, match.group(1)

    tiktok_pattern = r'(?:https?://)?(?:www\.|vm\.|m\.)?tiktok\.com/(?:@[^/]+/)?video/(\d+)'
    if match := re.match(tiktok_pattern, url):
        return bot.tiktok, match.group(1)

    bsky_patterbs = r'(?:https?://)?(?:www\.)?bsky\.app/profile/([^/]+)/post/([^/]+)'
    if match := re.match(bsky_patterbs, url):
        return bot.bsky, match.group(2)

    return None, None


async def send_webhook(title: str, load: str, color=None):
    # Create a rich embed
    if color is None:
        color = 5814783  # Blue color
    payload = {
        "embeds": [{
            "title": title,
            "description": load,
            "color": color,
        }]
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(LOGGER_WEBHOOK, json=payload) as response:
                if response.status == 204:
                    print(f"Successfully sent logger webhook: {load}")
                else:
                    print(f"Failed to send logger webhook. Status: {response.status}")
                return response.status
        except Exception as e:
            print(f"Error sending log webhook: {str(e)}")
            return None


class Base(Extension):
    def __init__(self, bot):
        self.bot = bot
        self.ready = False
        self.logger = logging.getLogger(__name__)
        self.task = Task(self.db_save_task, IntervalTrigger(seconds=60 * 30))  # save db every 30 minutes
        self.currently_downloading_for_embed = []

    @staticmethod
    async def _handle_timeout(ctx: SlashContext, url: str, amt: int):
        """Handle timeout for embed processing"""
        await asyncio.sleep(amt)
        if not ctx.responded:
            await ctx.send(f"An error occurred with your input `{url}` {create_nexus_str()}")

    @slash_command(name="save", description="Save Clyppy DB", scopes=[759798762171662399])
    async def save(self, ctx: SlashContext):
        await ctx.defer()
        await ctx.send("Saving DB...")
        await self.bot.guild_settings.save()
        await ctx.send("You can now safely exit.")

    @slash_command(name="vote", description="Vote on Clyppy to gain exclusive rewards!")
    async def vote(self, ctx: SlashContext):
        await ctx.send(embed=Embed(
            title="Vote for Clyppy!",
            description=f"Give Clyppy your support by voting in popular bot sites! By voting, receive the "
                        f"following benefits:\n\n- Exclusive role in [our Discord]({SUPPORT_SERVER_URL})\n\n"
                        f"View all the vote links below. Your support is appreciated.\n"
                        f"** - [Top.gg]({TOPGG_VOTE_LINK})**\n"
                        f"** - [InfinityBots]({INFINITY_VOTE_LINK})**\n"
                        f"** - [Dlist]({DLIST_VOTE_LINK})**\n"
                        f"** - [BotList.me]({BOTLISTME_VOTE_LINK})**{create_nexus_str()}")
        )

    @slash_command(name="embed", description="Embed a video link in this chat",
                   options=[SlashCommandOption(name="url",
                                               description="The YouTube, Twitch, etc. link to embed",
                                               required=True,
                                               type=OptionType.STRING)
                            ]
                   )
    async def embed(self, ctx: SlashContext, url: str):
        async def wait_for_download(clip_id: str, timeout: float = 30):
            start_time = time.time()
            while clip_id in self.currently_downloading_for_embed:
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Waiting for clip {clip_id} download timed out")
                await asyncio.sleep(0.1)

        timeout_task = None
        await ctx.defer(ephemeral=False)
        try:
            if not url.startswith("https://"):
                url = "https://" + url
            platform, slug = compute_platform(url, self.bot)
            if ctx.guild:
                guild = GuildType(ctx.guild.id, ctx.guild.name, False)
            else:
                guild = GuildType(ctx.author.id, ctx.author.username, True)
            self.logger.info(f"/embed in {guild.name} {url} -> {[platform.platform_name if platform is not None else None]}, {slug}")
            if platform is None:
                self.logger.info(f"return incompatible for /embed {url}")
                await ctx.send(f"Couldn't embed that url (invalid/incompatible) {create_nexus_str()}")
                return

            if slug in self.currently_downloading_for_embed:
                try:
                    await wait_for_download(slug)
                except TimeoutError:
                    pass  # continue with the dl anyway
            else:
                self.currently_downloading_for_embed.append(slug)

            timeout_task = asyncio.create_task(self._handle_timeout(ctx, url, 30))
            e = AutoEmbedder(self.bot, platform, logging.getLogger(__name__))
        except Exception as e:
            if timeout_task is not None:
                timeout_task.cancel()
            self.logger.info(f"Exception in /embed: {str(e)}")
            await ctx.send(f"Unexpected error while trying to embed this url {create_nexus_str()}")
            return
        try:
            await e._process_this_clip_link(
                parsed_id=slug,
                clip_link=url,
                respond_to=ctx,
                guild=guild,
                extended_url_formats=True,
                try_send_files=True
            )
        except NoDuration:
            await ctx.send(f"Couldn't embed that url (not a video post) {create_nexus_str()}")
        except VideoTooLong:
            await ctx.send(f"This video was too long to embed (longer than {MAX_VIDEO_LEN_SEC / 60} minutes) {create_nexus_str()}")
        except ClipFailure:
            await ctx.send(f"Unexpected error while trying to download this clip {create_nexus_str()}")
        except Exception as e:
            self.logger.info(f'Unexpected error in /embed: {str(e)}')
            await ctx.send(f"An unexpected error occurred with your input `{url}` {create_nexus_str()}")
        finally:
            timeout_task.cancel()
            try:
                self.currently_downloading_for_embed.remove(slug)
            except ValueError:
                pass

    @slash_command(name="help", description="Get help using Clyppy")
    async def help(self, ctx: SlashContext):
        await ctx.defer()
        about = (
            "Clyppy automatically converts video links into native Discord embeds! Share videos from YouTube, Twitch, Reddit, and more directly in chat.\n\n"
            "**TROUBLESHOOTING**\nIf Clyppy isn't responding to your links, please check that it has the correct permissions in your Discord channel."
            " Required permissions are: `Send Links`, `Send Messages`\n\n"
            "**UPDATE Dec 3rd 2024** Clyppy is back online after a break. We are working on improving the service and adding new features. Stay tuned!")
        help_embed = Embed(title="ABOUT CLYPPY", description=about)
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
    #        guild_ctx=GuildType(ctx.guild.id, ctx.guild.name, True),
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
        if ctx.guild is None:
            await ctx.send("This command is only available in servers.")
            return
        if ctx.guild.id == ctx.author.id:  # in case they patch the "dm guild is None" situation
            await ctx.send("This command is only available in servers.")
            return

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
                               f"More info:\nTried to retrieve channel <#{ec}> but failed.")
                    self.bot.guild_settings.set_error_channel(ctx.guild.id, 0)
                    return await ctx.send("Current error channel: " + cur_chn)

        await ctx.defer()
        if ctx.guild is None:
            await ctx.send("This command is only available in servers.")
            return
        if (e := self.bot.get_channel(error_channel)) is None:
            return await ctx.send(f"Channel #{error_channel} not found.\n\n"
                                  f"Please make sure Clyppy has the `VIEW_CHANNELS` permission & try again.")
        res = self.bot.guild_settings.set_error_channel(ctx.guild.id, e.id)
        if res:
            return await ctx.send(f"Success! Error channel set to {e.mention}")
        else:
            return await ctx.send("An error occurred while setting the error channel. Please try again.")

    @slash_command(name="settings", description="Display or change Clyppy's miscellaneous settings",
                   options=[SlashCommandOption(name="quickembeds", type=OptionType.BOOLEAN,
                                               description="Should Clyppy respond to links? True=enabled, False=disabled, default=True",
                                               required=False),
                            SlashCommandOption(name="on_error", type=OptionType.STRING,
                                               description="Choose what Clyppy should do upon error",
                                               required=False),
                            SlashCommandOption(name="embed_buttons", type=OptionType.STRING,
                                               description="Configure what buttons Clyppy shows when embedding clips",
                                               required=False)])
    async def settings(self, ctx: SlashContext, quickembeds: bool = None, on_error: str = None, embed_buttons: str = None):
        await ctx.defer()
        if ctx.guild is None:
            await ctx.send("This command is only available in servers.")
            return
        if ctx.guild.id == ctx.author.id:
            await ctx.send("This command is only available in servers.")
            return

        if not ctx.author.has_permission(Permissions.ADMINISTRATOR):
            await self._send_settings_help(ctx, True)
            return

        if on_error is None and embed_buttons is None and quickembeds is None:
            await self._send_settings_help(ctx, False)
            return

        current_embed_setting = self.bot.guild_settings.get_embed_enabled(ctx.guild.id)
        chosen_embed = current_embed_setting
        if quickembeds is not None:
            chosen_embed = quickembeds
            self.bot.guild_settings.set_embed_enabled(ctx.guild.id, quickembeds)

        # Get current settings
        current_setting = self.bot.guild_settings.get_setting(ctx.guild.id)
        current_on_error = POSSIBLE_ON_ERRORS[int(current_setting[1])]

        # Use current values if not specified
        on_error = on_error or current_on_error

        if on_error not in POSSIBLE_ON_ERRORS:
            await ctx.send(f"Option '{on_error}' not a valid **on_error** setting!\n"
                           f"Must be one of `{POSSIBLE_ON_ERRORS}`")
            return

        err_idx = POSSIBLE_ON_ERRORS.index(on_error)

        # Handle embed settings
        current_embed_setting: int = self.bot.guild_settings.get_embed_buttons(ctx.guild.id)
        current_embed_setting: str = POSSIBLE_EMBED_BUTTONS[current_embed_setting]
        embed_buttons = embed_buttons or current_embed_setting  # switch to current_embed_setting if it's not None

        if embed_buttons not in POSSIBLE_EMBED_BUTTONS:
            await ctx.send(f"Option '{embed_buttons}' not a valid **embed_buttons** setting!\n"
                           f"Must be one of `{POSSIBLE_EMBED_BUTTONS}`")
            return

        embed_idx = POSSIBLE_EMBED_BUTTONS.index(embed_buttons)

        self.bot.guild_settings.set_embed_buttons(ctx.guild.id, embed_idx)

        chosen_embed = "enabled" if chosen_embed else "disabled"
        await ctx.send(
            "Successfully changed settings:\n\n"
            f"**quickembeds**: {chosen_embed}\n"
            f"**on_error**: {on_error}\n"
            f"**embed_buttons**: {embed_buttons}"
        )

    async def _send_settings_help(self, ctx: SlashContext, prepend_admin: bool = False):
        cs = self.bot.guild_settings.get_setting_str(ctx.guild.id)
        es = self.bot.guild_settings.get_embed_buttons(ctx.guild.id)
        qe = self.bot.guild_settings.get_embed_enabled(ctx.guild.id)
        qe = "enabled" if qe else "disabled"
        es = POSSIBLE_EMBED_BUTTONS[es]
        about = (
            '**Configurable Settings:**\n'
            'Below are the settings you can configure using this command. Each setting name is in **bold** '
            'followed by its available options.\n\n'
            '**quickembeds** Should Clyppy automatically respond to links sent in this server? If disabled, '
            'users can still embed videos using the `/embed` command.\n'
            ' - `True`: enabled\n'
            ' - `False`: disabled\n\n'
            '**on_error** Choose what Clyppy does when it encounters an error:\n'
            ' - `info`: Respond to the message with the error.\n'
            ' - `dm`: DM the message author about the error.\n\n'
            '**embed_buttons** Choose which buttons Clyppy shows under embedded videos:\n'
            ' - `none`: No buttons, just the video.\n'
            ' - `view`: A button to the original clip.\n'
            ' - `dl`: A button to download the original video file (on compatible clips).\n'
            ' - `all`: Shows all available buttons.\n\n'
            f'**Current Settings:**\n**quickembeds**: {qe}\n{cs}\n**embed_buttons**: {es}\n\n'
            f'Something missing? Please **[Suggest a Feature]({SUPPORT_SERVER_URL})**'
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
            w = None
            if event.guild.widget_enabled:
                w = await event.guild.fetch_widget()
            await send_webhook(
                title=f'Joined new guild: {event.guild.name}',
                load=f"id - {event.guild.id}\n"
                     f"large - {event.guild.large}\n"
                     f"members - {event.guild.member_count}\n"
                     f"widget - {w}\n",
                color=65280  # green
            )
            await self.post_servers(len(self.bot.guilds))

    @listen()
    async def on_guild_left(self, event: GuildLeft):
        if self.ready:
            self.logger.info(f'Left guild: {event.guild.name}')
            w = None
            if event.guild.widget_enabled:
                w = await event.guild.fetch_widget()
            await send_webhook(
                title=f'Left guild: {event.guild.name}',
                load=f"id - {event.guild.id}\n"
                     f"large - {event.guild.large}\n"
                     f"members - {event.guild.member_count}\n"
                     f"widget - {w}\n",
                color=16711680  # red
            )
            await self.post_servers(len(self.bot.guilds))

    @listen()
    async def on_ready(self):
        if not self.ready:
            self.ready = True
            self.logger.info(f"bot logged in as {self.bot.user.username}")
            self.logger.info(f"total shards: {len(self.bot.shards)}")
            self.logger.info(f"my guilds: {len(self.bot.guilds)}")
            self.logger.info(f"CLYPPY VERSION: {VERSION}")
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
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.botlist.me/api/v1/bots/1111723928604381314/stats",
                                    json={'server_count': num,
                                          'shard_count': 1},
                                    headers={'authorization': os.getenv('BOTLISTME_TOKEN')}) as resp:
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
