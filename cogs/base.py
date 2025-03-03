from bot.classes import BaseMisc
from bot.errors import VideoTooLong, NoDuration, ClipFailure, NoPermsToView
from interactions import (Extension, Embed, slash_command, SlashContext, SlashCommandOption, OptionType, listen,
    Permissions, ActivityType, Activity, Task, IntervalTrigger, ComponentContext, component_callback, TYPE_THREAD_CHANNEL)
from bot.tools.misc import SUPPORT_SERVER_URL, TOPGG_VOTE_LINK, create_nexus_str
from bot.env import POSSIBLE_ON_ERRORS, POSSIBLE_EMBED_BUTTONS, INFINITY_VOTE_LINK, LOGGER_WEBHOOK, APPUSE_LOG_WEBHOOK, \
    VERSION, DLIST_VOTE_LINK, MAX_VIDEO_LEN_SEC, EMBED_TOKEN_COST, EMBED_W_TOKEN_MAX_LEN
from interactions.api.events.discord import GuildJoin, GuildLeft
from bot.tools.embedder import AutoEmbedder
from bot.io import get_aiohttp_session
from bot.types import GuildType, COLOR_GREEN, COLOR_RED
from typing import Tuple, Optional
from re import compile
import asyncio
import logging
import aiohttp
import time
import os


def compute_platform(url: str, bot) -> Tuple[Optional[BaseMisc], Optional[str]]:
    """Determine the platform and clip ID from the URL"""
    for this_platform in bot.platform_list:
        if slug := this_platform.parse_clip_url(url):
            return this_platform, slug

    return None, None


async def send_webhook(title: str, load: str, color=None, url=None, in_test=False):
    if not in_test and os.getenv("TEST"):
        return

    if url is None:
        url = LOGGER_WEBHOOK

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
            async with session.post(url, json=payload) as response:
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
        self.save_task = Task(self.db_save_task, IntervalTrigger(seconds=60 * 30))  # save db every 30 minutes
        self.currently_downloading_for_embed = []
        self.currently_embedding_users = []

    @staticmethod
    async def _fetch_tokens(user):
        url = 'https://clyppy.io/api/tokens/get/'
        headers = {
            'X-API-Key': os.getenv('clyppy_post_key'),
            'Content-Type': 'application/json'
        }
        j = {'userid': user.id, 'username': user.username}
        async with get_aiohttp_session() as session:
            async with session.get(url, json=j, headers=headers) as response:
                if response.status == 200:
                    j = await response.json()
                    return j['tokens']
                else:
                    error_data = await response.json()
                    raise Exception(f"Failed to fetch user's VIP tokens: {error_data.get('error', 'Unknown error')}")

    @staticmethod
    async def _handle_timeout(ctx: SlashContext, url: str, amt: int):
        """Handle timeout for embed processing"""
        await asyncio.sleep(amt)
        if not ctx.responded:
            await ctx.send(f"An error occurred with your input `{url}` {create_nexus_str()}")
            raise TimeoutError(f"Waiting for clip {url} download timed out")

    @staticmethod
    async def get_clip_info(clip_id: str):
        """Get clip info from clyppyio"""
        url = f"https://clyppy.io/api/clips/get/{clip_id}"
        headers = {
            'X-API-Key': os.getenv('clyppy_post_key'),
            'Content-Type': 'application/json'
        }
        async with get_aiohttp_session() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    j = await response.json()
                    return j
                elif response.status == 404:
                    return {'match': False}
                else:
                    raise Exception(f"Failed to get clip info: (Server returned code: {response.status})")

    @component_callback(compile(r"ibtn-.*"))
    async def info_button_response(self, ctx: ComponentContext):
        """
        This function gets called whenever a user clicks an info button.
        """
        await ctx.defer(ephemeral=True)
        clyppyid = ctx.custom_id.split("-")[1]
        try:
            clip_info = await self.get_clip_info(clyppyid)
            self.logger.info(f"@component_callback for button {ctx.custom_id} - clip_info: {clip_info}")
            if clip_info['match']:
                clyppy_cdn = 'https://clyppy.io/media/' in clip_info['url'] or 'https://cdn.clyppy.io' in clip_info['url']
                original = int(clip_info['requested_by'])

                embed = Embed(title=f"{clip_info['title']}")
                embed.add_field(name="Platform", value=clip_info['platform'])
                embed.add_field(name="Original URL", value=clip_info['embedded_url'])
                embed.add_field(name="Requested by", value=f'<@{ctx.author.id}>')
                if ctx.author.id != original:
                    embed.add_field(name="First requester", value=f"<@{original}>")
                embed.add_field(name="Duration", value=f"{clip_info['duration'] // 60}m {round(clip_info['duration'] % 60, 2)}s")
                embed.add_field(name="File Location", value=clip_info['url'] if clyppy_cdn else f"Hosted on {clip_info['platform']}'s cdn")
                if clyppy_cdn:
                    embed.add_field(name="Expires", value=f"{clip_info['expiry_ts_str']}")
                await ctx.send(embed=embed)
                await send_webhook(
                    title=f'{["DM" if ctx.guild is None else ctx.guild.name]} - \'info\' called on {clyppyid}',
                    load=f"response - success"
                         f"title: {clip_info['title']}\n"
                         f"url: {clip_info['embedded_url']}\n"
                         f"platform: {clip_info['platform']}\n"
                         f"duration: {clip_info['duration']}\n"
                         f"file_location: {clip_info['url'] if clyppy_cdn else 'Hosted on ' + str(clip_info['platform']) + ' cdn'}"
                         f"expires: {[clip_info['expiry_ts_str'] if clyppy_cdn else 'N/A']}",
                    color=COLOR_GREEN,
                    url=APPUSE_LOG_WEBHOOK
                )
            else:
                await ctx.send(f"Uh oh... it seems the clip {clyppyid} doesn't exist!")
                await send_webhook(
                    title=f'{["DM" if ctx.guild is None else ctx.guild.name]} - \'info\' called on {clyppyid}',
                    load=f"response - error clip not found",
                    color=COLOR_RED,
                    url=APPUSE_LOG_WEBHOOK
                )
        except Exception as e:
            self.logger.info(f"@component_callback for button {ctx.custom_id} - Error: {e}")
            await ctx.send(f"Uh oh... an error occurred fetching the clip {clyppyid}")
            await send_webhook(
                title=f'{["DM" if ctx.guild is None else ctx.guild.name]} - \'info\' called on {clyppyid}',
                load=f"response - unexpected error: {e}",
                color=COLOR_RED,
                url=APPUSE_LOG_WEBHOOK
            )

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
                        f"following benefits:\n\n"
                        f"- Exclusive role in [our Discord]({SUPPORT_SERVER_URL})\n"
                        f"- (2) VIP tokens per vote!\n"
                        f"- VIP tokens allow you to embed videos up to {EMBED_W_TOKEN_MAX_LEN // 60} minutes in length!\n\n"
                        f"View all the vote links below. Your support is appreciated.\n\n"
                        f"** - [Top.gg]({TOPGG_VOTE_LINK})**\n"
                        f"** - [InfinityBots]({INFINITY_VOTE_LINK})**\n"
                        f"** - [DiscordBotList]({DLIST_VOTE_LINK})**\n"
                        #f"** - [BotList.me]({BOTLISTME_VOTE_LINK})**"
                        f"{create_nexus_str()}"
        ))
        await send_webhook(
            title=f'{["DM" if ctx.guild is None else ctx.guild.name]} - /vote called',
            load=f"response - success",
            color=COLOR_GREEN,
            url=APPUSE_LOG_WEBHOOK
        )

    @slash_command(name="tokens", description="View your VIP tokens!")
    async def tokens(self, ctx: SlashContext):
        await ctx.defer()
        tokens = await self._fetch_tokens(ctx.user)
        await ctx.send(f"You have `{tokens}` VIP tokens!\n"
                       f"You can gain more by **voting** with `/vote`\n\n"
                       f"Use your VIP tokens to embed longer videos with Clyppy (up to {EMBED_W_TOKEN_MAX_LEN // 60} minutes!)")
        await send_webhook(
            title=f'{["DM" if ctx.guild is None else ctx.guild.name]} - /tokens called',
            load=f"response - success",
            color=COLOR_GREEN,
            url=APPUSE_LOG_WEBHOOK
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

        if ctx.guild:
            guild = GuildType(ctx.guild.id, ctx.guild.name, False)
            ctx_link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}"
        else:
            guild = GuildType(ctx.author.id, ctx.author.username, True)
            ctx_link = f"https://discord.com/channels/@me/{ctx.bot.user.id}"

        slug, p = None, None
        try:
            if not url.startswith("https://"):
                url = "https://" + url
            platform, slug = compute_platform(url, self.bot)

            p = platform.platform_name if platform is not None else None
            self.logger.info(f"/embed in {guild.name} {url} -> {p}, {slug}")

            if guild.is_dm:
                nsfw_enabed = True
            elif isinstance(ctx.channel, TYPE_THREAD_CHANNEL):
                # GuildPublicThread has no attribute nsfw
                nsfw_enabed = False
            else:
                nsfw_enabed = ctx.channel.nsfw

            if platform is None:
                self.logger.info(f"return incompatible for /embed {url}")
                await ctx.send(f"Couldn't embed that url (invalid/incompatible) {create_nexus_str()}")
                await send_webhook(
                    title=f'{["DM" if guild.is_dm else guild.name]} - /embed called - Failure',
                    load=f"user - {ctx.user.username}\n"
                         f"cmd - /embed url:{url}\n"
                         f"platform: {p}\n"
                         f"slug: {slug}\n"
                         f"response - Incompatible",
                    color=COLOR_RED,
                    url=APPUSE_LOG_WEBHOOK
                )
                return
            elif platform.is_nsfw and not nsfw_enabed:
                await ctx.send(f"This platform is not allowed in this channel. You can either:\n"
                               f" - If you're a server admin, go to `Edit Channel > Overview` and toggle `Age-Restricted Channel`\n"
                               f" - If you're not an admin, you can invite me to one of your servers, and then create a new age-restricted channel there\n"
                               f"\n**Note** for iOS users, due to the Apple Store's rules, you may need to access [discord.com]({ctx_link}) in your phone's browser to enable this.\n")
                await send_webhook(
                    title=f'{["DM" if guild.is_dm else guild.name]} - /embed called - Failure',
                    load=f"user - {ctx.user.username}\n"
                         f"cmd - /embed url:{url}\n"
                         f"platform: {p}\n"
                         f"slug: {slug}\n"
                         f"response - NSFW disabled",
                    color=COLOR_RED,
                    url=APPUSE_LOG_WEBHOOK
                )
                return

            if ctx.user.id in self.currently_embedding_users:
                await ctx.send(f"You're already embedding a video. Please wait for it to finish before trying again.")
                await send_webhook(
                    title=f'{["DM" if guild.is_dm else guild.name]} - /embed called - Failure',
                    load=f"user - {ctx.user.username}\n"
                         f"cmd - /embed url:{url}\n"
                         f"platform: {p}\n"
                         f"slug: {slug}\n"
                         f"response - Already embedding",
                    color=COLOR_RED,
                )
                return
            else:
                self.currently_embedding_users.append(ctx.user.id)

            if slug in self.currently_downloading_for_embed:
                try:
                    # if its already downloading from another embed command running at the same time
                    await wait_for_download(slug, timeout=platform.dl_timeout_secs)
                except TimeoutError:
                    pass  # continue with the dl anyway
            else:
                self.currently_downloading_for_embed.append(slug)

            timeout_task = asyncio.create_task(self._handle_timeout(ctx, url, platform.dl_timeout_secs))
            e = AutoEmbedder(self.bot, platform, logging.getLogger(__name__))
        except Exception as e:
            if timeout_task is not None:
                timeout_task.cancel()
            self.logger.info(f"Exception in /embed: {str(e)}")
            await ctx.send(f"Unexpected error while trying to embed this url {create_nexus_str()}")
            await send_webhook(
                title=f'{["DM" if guild.is_dm else guild.name]} - /embed called - Failure',
                load=f"user - {ctx.user.username}\n"
                     f"cmd - /embed url:{url}\n"
                     f"platform: {p}\n"
                     f"slug: {slug}\n"
                     f"response - Unexpected error",
                color=COLOR_RED,
                url=APPUSE_LOG_WEBHOOK
            )
            return

        success, response = False, "Unknown error"
        try:
            await e._process_this_clip_link(
                clip_link=url,
                respond_to=ctx,
                guild=guild,
                extended_url_formats=True,
                try_send_files=True
            )
            success, response = True, "Success"
        except NoDuration:
            await ctx.send(f"Couldn't embed that url (not a video post) {create_nexus_str()}")
            success, response = False, "No duration"
        except NoPermsToView:
            await ctx.send(f"Couldn't embed that url (no permissions to view) {create_nexus_str()}")
            success, response = False, "No permisions"
        except VideoTooLong:
            if await self._fetch_tokens(ctx.user) >= EMBED_TOKEN_COST:
                await ctx.send(f"This video was too long to embed (longer than {MAX_VIDEO_LEN_SEC / 60} minutes)\n"
                               f"It's also longer than {EMBED_W_TOKEN_MAX_LEN // 60} minutes, so using your VIP tokens wouldn't work either...")
            else:
                await ctx.send(f"This video was too long to embed (longer than {MAX_VIDEO_LEN_SEC / 60} minutes)\n"
                               f"Voting with `/vote` will increase it to {EMBED_W_TOKEN_MAX_LEN // 60} minutes! {create_nexus_str()}")
            success, response = False, "Video too long"
        except ClipFailure:
            await ctx.send(f"Unexpected error while trying to download this clip {create_nexus_str()}")
            success, response = False, "Clip failure"
        except Exception as e:
            self.logger.info(f'Unexpected error in /embed: {str(e)}')
            await ctx.send(f"An unexpected error occurred with your input `{url}` {create_nexus_str()}")
            success, response = False, "Unexpected error"
        finally:
            timeout_task.cancel()

            await send_webhook(
                title=f'{["DM" if guild.is_dm else guild.name]} - /embed called - {["Success" if success else "Failure"]}',
                load=f"user - {ctx.user.username}\n"
                     f"cmd - /embed url:{url}\n"
                     f"platform: {p}\n"
                     f"slug: {slug}\n"
                     f"response - {response}",
                color=[COLOR_GREEN if success else COLOR_RED],
                url=APPUSE_LOG_WEBHOOK
            )
            try:
                self.currently_downloading_for_embed.remove(slug)
            except ValueError:
                pass
            try:
                self.currently_embedding_users.remove(ctx.user.id)
            except ValueError:
                pass

    #@slash_command(name="alerts", description="Configure Clyppy Alerts (Live Notifications, Video Uploads, etc.")
    #async def alerts(self, ctx: SlashContext):
    #    pass

    @slash_command(name="help", description="Get help using Clyppy")
    async def help(self, ctx: SlashContext):
        await ctx.defer()
        about = (
            "Clyppy converts video links into native Discord embeds! Share videos from YouTube, Twitch, Reddit, and more directly in chat.\n\n"
            "I will automatically respond to Twitch and Kick clips, and all other compatible platforms are only accessibly through `/embed`\n\n"
            "**UPDATE Dec 3rd 2024** Clyppy is back online after a break. We are working on improving the service and adding new features. Stay tuned!\n\n"
            "**COMING SOON** We're working on adding server customization for Clyppy, so you can choose which platforms I will automatically reply to!\n\n"
            f"---------------------------------\n"
            f"Join our [Discord server]({SUPPORT_SERVER_URL}) for more info and to get updates!")
        help_embed = Embed(title="ABOUT CLYPPY", description=about)
        help_embed.description += create_nexus_str()
        help_embed.footer = f"CLYPPY v{VERSION}"
        await ctx.send(
            content="Clyppy is a social bot that makes sharing videos easier!",
            embed=help_embed)
        await send_webhook(
            title=f'{["DM" if ctx.guild is None else ctx.guild.name]} - /help called',
            load=f"response - success",
            color=COLOR_GREEN,
            url=APPUSE_LOG_WEBHOOK
        )

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
                                               required=False),
                            SlashCommandOption(name="nsfw", type=OptionType.BOOLEAN,
                                               description="Should users in this server be allowed to embed videos which are not safe for work?",
                                               required=False
                                               )])
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
            f"**embed_buttons**: {embed_buttons}\n\n"
        )

    async def _send_settings_help(self, ctx: SlashContext, prepend_admin: bool = False):
        cs = self.bot.guild_settings.get_setting_str(ctx.guild.id)
        es = self.bot.guild_settings.get_embed_buttons(ctx.guild.id)
        qe = self.bot.guild_settings.get_embed_enabled(ctx.guild.id)

        es = POSSIBLE_EMBED_BUTTONS[es]
        qe = "enabled" if qe else "disabled"
        about = (
            '**Configurable Settings:**\n'
            'Below are the settings you can configure using this command. Each setting name is in **bold** '
            'followed by its available options.\n\n'
            '**quickembeds** [Available for Twitch & Kick clips] Should Clyppy automatically respond to links sent in this server? If disabled, '
            'users can still embed videos using the `/embed` command.\n'
            ' - `True`: enabled\n'
            ' - `False`: disabled (default)\n\n'
            '**on_error** Choose what Clyppy does when it encounters an error:\n'
            ' - `info`: Respond to the message with the error.\n'
            ' - `dm`: DM the message author about the error.\n\n'
            '**embed_buttons** Choose which buttons Clyppy shows under embedded videos:\n'
            ' - `none`: No buttons, just the video.\n'
            ' - `view`: A button to the original clip.\n'
            ' - `dl`: A button to download the original video file (on compatible clips).\n'
            ' - `all`: Shows all available buttons.\n\n'
            '**nsfw** Should users in this server be allowed to embed videos which are not safe for work?:\n'
            ' - `True`: Allow NSFW videos to be embedded in this server\n'
            ' - `False`: NSFW videos won\'t be embedded (default)\n\n'
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
                color=COLOR_GREEN
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
                color=COLOR_RED
            )
            await self.post_servers(len(self.bot.guilds))

    @listen()
    async def on_ready(self):
        if not self.ready:
            self.ready = True
            self.save_task.start()
            self.logger.info(f"bot logged in as {self.bot.user.username}")
            self.logger.info(f"total shards: {len(self.bot.shards)}")
            self.logger.info(f"my guilds: {len(self.bot.guilds)}")
            self.logger.info(f"CLYPPY VERSION: {VERSION}")
            if os.getenv("TEST") is not None:
                await self.post_servers(len(self.bot.guilds))
            self.logger.info("--------------")
            await self.bot.change_presence(
                activity=Activity(type=ActivityType.STREAMING, name="/help", url="https://twitch.tv/hesmen"))

    async def post_servers(self, num: int):
        if os.getenv("TEST") is not None:
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://top.gg/api/bots/1111723928604381314/stats", json={'server_count': num},
                                        headers={'Authorization': os.getenv('GG_TOKEN')}) as resp:
                    await resp.text()
        except:
            self.logger.info(f"Failed to post servers to top.gg: code {resp.status}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.botlist.me/api/v1/bots/1111723928604381314/stats",
                                        json={'server_count': num,
                                              'shard_count': 1},
                                        headers={'authorization': os.getenv('BOTLISTME_TOKEN')}) as resp:
                    await resp.json()
        except:
            self.logger.info(f"Failed to post servers to botlist.me: {await resp.text()}")

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
