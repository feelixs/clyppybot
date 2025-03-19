import asyncio

from bot.classes import BaseMisc, send_webhook
from interactions import (Extension, Embed, slash_command, SlashContext, SlashCommandOption, OptionType, listen,
                          Permissions, ActivityType, Activity, Task, IntervalTrigger, ComponentContext, Message,
                          component_callback, Button, ButtonStyle)
from bot.env import SUPPORT_SERVER_URL, create_nexus_str
from bot.env import POSSIBLE_ON_ERRORS, POSSIBLE_EMBED_BUTTONS, APPUSE_LOG_WEBHOOK, VERSION, EMBED_TXT_COMMAND
from interactions.api.events.discord import GuildJoin, GuildLeft, MessageCreate, InviteCreate
from bot.io import get_aiohttp_session, callback_clip_delete_msg, add_reqqed_by
from bot.types import COLOR_GREEN, COLOR_RED
from typing import Tuple, Optional
from re import compile
import logging
import aiohttp
import os


def compute_platform(url: str, bot) -> Tuple[Optional[BaseMisc], Optional[str]]:
    """Determine the platform and clip ID from the URL"""
    for this_platform in bot.platform_list:
        if slug := this_platform.parse_clip_url(url):
            return this_platform, slug

    return None, None


class Base(Extension):
    def __init__(self, bot):
        self.bot = bot
        self.ready = False
        self.logger = logging.getLogger(__name__)
        self.save_task = Task(self.db_save_task, IntervalTrigger(seconds=60 * 30))  # save db every 30 minutes
        self.base_embedder = self.bot.base_embedder.embedder

    @listen(MessageCreate)
    async def on_message_create(self, event: MessageCreate):
        if event.message.author.bot:
            return

        # check for text commands
        msg = event.message.content
        split = msg.split(' ')
        if msg.startswith(EMBED_TXT_COMMAND):
            if len(split) <= 1:
                return await event.message.reply("Please provide a URL to embed like `.embed https://example.com`")
            # handle .embed command
            words = self.base_embedder.get_words(event.message.content)
            for p in self.bot.platform_embedders:
                contains_clip_link, _ = p.embedder.get_next_clip_link_loc(
                    words=words,
                    n=0,
                    print=False
                )
                if contains_clip_link:
                    return await p.handle_message(event)

        if len(split) > 1:
            # other misc commands don't take arguments
            return

        msg = msg.strip()
        for txt_command, func in self.bot.base_embedder.OTHER_TXT_COMMANDS.items():
            if msg == txt_command:
                return await func(event.message)

        # handle quickembed links -> both .embed and quickembed
        # will use the same function, and will both do checks to ensure if it should continue
        # but structuring like this will reduce unwanted calls handle_message()
        words = self.base_embedder.get_words(event.message.content)
        for p in self.bot.platform_embedders:
            if p.is_base:
                continue  # don't use autoembed on base embed (bot.base -> raw yt-dlp)
            contains_clip_link, _ = p.embedder.get_next_clip_link_loc(
                words=words,
                n=0,
                print=False
            )
            if contains_clip_link:
                return await p.handle_message(event)

    @staticmethod
    async def get_clip_info(clip_id: str, ctx_type='StoredVideo'):
        """Get clip info from clyppyio"""
        url = f"https://clyppy.io/api/clips/get/{clip_id}"
        headers = {
            'X-API-Key': os.getenv('clyppy_post_key'),
            'Request-Type': ctx_type,
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

        clip_ctx = ctx.custom_id.split("-")
        clyppyid = clip_ctx[-1]
        is_discord_uploaded = clip_ctx[1] == "d"  # was it a discord upload

        buttons = [
            Button(
                style=ButtonStyle.DANGER,
                label="X",
                custom_id=f"ibtn-delete-d-{clyppyid}" if is_discord_uploaded else f"ibtn-delete-{clyppyid}"
            ),
            Button(style=ButtonStyle.LINK, label=f"View your clips", url='https://clyppy.io/profile/clips')
        ]

        try:
            clyppy_cdn = False

            clip_info = await self.get_clip_info(clyppyid, ctx_type='BotInteraction' if is_discord_uploaded else 'StoredVideo')
            self.logger.info(f"@component_callback for button {ctx.custom_id} - clip_info: {clip_info}")
            if clip_info['match']:
                clip_url = clip_info['url']

                original = clip_info['requested_by']
                if original is not None:
                    original = int(original)

                deleted = clip_info['is_deleted']
                dstr = clip_info['deleted_at_str']

                dyr = clip_info['duration']
                if dyr is None:
                    dyr = 0

                embed = Embed(title=f"{clip_info['title']}")
                if original is not None:
                    embed.add_field(name="Command", value=f"<@{original}> used `.embed {clip_info['embedded_url']}`")
                    #embed.add_field(name="Requested by", value=f'<@{original}>')
                else:
                    embed.add_field(name="Command", value=f"`.embed {clip_info['embedded_url']}`")

                if clip_info['platform'] != 'base':
                    embed.add_field(name="Platform", value=clip_info['platform'])

                embed.add_field(
                    name="Duration",
                    value=f"{dyr // 60}m {round(dyr % 60, 2)}s"
                )

                if not is_discord_uploaded:
                    clyppy_cdn = 'https://clyppy.io/media/' in clip_url or 'https://cdn.clyppy.io' in clip_url
                    embed.add_field(
                        name="File Location",
                        value=clip_url if clyppy_cdn else f"Hosted on {clip_info['platform']}'s cdn"
                    )
                    if clyppy_cdn and not deleted:
                        embed.add_field(name="Expires", value=f"{clip_info['expiry_ts_str']}")
                    elif clyppy_cdn and deleted:
                        embed.add_field(name="Deleted", value=dstr if dstr is not None else "True")

                await ctx.send(embed=embed, components=buttons)

                if not is_discord_uploaded:
                    # from external/clyppy cdn
                    await send_webhook(
                        title=f'{"DM" if ctx.guild is None else ctx.guild.name}, {ctx.author.username} - \'info\' called on {clyppyid}',
                        load=f"response - success"
                             f"title: {clip_info['title']}\n"
                             f"url: {clip_info['embedded_url']}\n"
                             f"platform: {clip_info['platform']}\n"
                             f"duration: {dyr}\n"
                             f"file_location: {clip_info['url'] if clyppy_cdn else 'Hosted on ' + str(clip_info['platform']) + ' cdn'}\n"
                             f"expires: {clip_info['expiry_ts_str'] if clyppy_cdn else 'N/A'}"
                             f"deleted: {deleted}",
                        color=COLOR_GREEN,
                        url=APPUSE_LOG_WEBHOOK,
                        logger=self.logger
                    )
                else:
                    # uploaded to discord
                    await send_webhook(
                        title=f'{"DM" if ctx.guild is None else ctx.guild.name}, {ctx.author.username} - \'info\' called on {clyppyid}',
                        load=f"response - success"
                             f"title: {clip_info['title']}\n"
                             f"url: {clip_info['embedded_url']}\n"
                             f"platform: {clip_info['platform']}\n"
                             f"duration: {dyr}\n",
                        color=COLOR_GREEN,
                        url=APPUSE_LOG_WEBHOOK,
                        logger=self.logger
                    )
            else:
                await ctx.send(f"Uh oh... it seems the clip {clyppyid} doesn't exist!")
                await send_webhook(
                    title=f'{"DM" if ctx.guild is None else ctx.guild.name}, {ctx.author.username} - \'info\' called on {clyppyid}',
                    load=f"response - error clip not found",
                    color=COLOR_RED,
                    url=APPUSE_LOG_WEBHOOK,
                    logger=self.logger
                )
        except Exception as e:
            self.logger.info(f"@component_callback for button {ctx.custom_id} - Error: {e}")
            await ctx.send(f"Uh oh... an error occurred fetching the clip {clyppyid}")
            await send_webhook(
                title=f'{"DM" if ctx.guild is None else ctx.guild.name}, {ctx.author.username} - \'info\' called on {clyppyid}',
                load=f"response - unexpected error: {e}",
                color=COLOR_RED,
                url=APPUSE_LOG_WEBHOOK,
                logger=self.logger
            )

    @component_callback(compile(r"ibtn-delete-.*"))
    async def delete_button_response(self, ctx: ComponentContext):
        clip_ctx = ctx.custom_id.split("-")
        clyppyid = clip_ctx[-1]
        is_discord_uploaded = clip_ctx[-2] == "d"

        await ctx.send(
            content=f"Are you sure you want to continue? This will delete all CLYPPY embeds you\'ve requested of this clip.",
            ephemeral=True,
            components=[
                Button(
                    style=ButtonStyle.SUCCESS,
                    label="Confirm",
                    custom_id=f"ibtn-confirm-delete-d-{clyppyid}" if is_discord_uploaded else f"ibtn-confirm-delete-{clyppyid}"
                )
            ]
        )

    @component_callback(compile(r"ibtn-confirm-delete-.*"))
    async def confirm_delete_button_response(self, ctx: ComponentContext):
        await ctx.defer(ephemeral=True)
        clip_ctx = ctx.custom_id.split("-")
        clyppyid = clip_ctx[-1]
        is_discord_uploaded = clip_ctx[-2] == "d"

        success_codes = [200, 201, 404]  # all the status codes where we wouldn't want to re-add reqqed by on error

        self.logger.info(f"{ctx.message.id}, {ctx.id}, {ctx.message_id}")
        data = {"video_id": clyppyid, "user_id": ctx.author.id, "msg_id": ctx.message.id}
        try:
            response = await callback_clip_delete_msg(
                data=data,
                key=os.getenv('clyppy_post_key'),
                ctx_type='BotInteraction' if is_discord_uploaded else 'StoredVideo'
            )
            self.logger.info(f"@component_callback for button {ctx.custom_id} - response: {response}")
            if response['code'] == 401:
                raise Exception(f"Unauthorized: User <@{ctx.author.id}> did not embed this clip!")
            elif response['code'] not in success_codes:
                raise Exception(f"Error: {response['code']}")
            elif response['ctx'] is not None:
                # maybe there's more than 1 message by this user of this clip
                delete_tasks = []
                for clip in response['ctx']:
                    try:
                        # clyppy uploads the clip to clyppyio with the serverid as the userid if it's uploaded inside that user's DM with CLYPPY
                        is_dm = str(clip['server_id']) == str(ctx.author.id)
                        if is_dm:
                            chn = await ctx.author.fetch_dm(force=False)
                            msg: Message = await chn.fetch_message(clip['message_id'])
                        else:
                            chn = await self.bot.fetch_channel(clip['channel_id'])
                            msg: Message = await chn.fetch_message(clip['message_id'])
                        delete_tasks.append(asyncio.create_task(msg.delete()))
                    except Exception as e:
                        self.logger.info(f"@component_callback for button {ctx.custom_id} - Could not delete message {clip['message_id']} from channel {clip['channel_id']}: {str(e)}")
                await asyncio.gather(*delete_tasks)

        except Exception as e:
            self.logger.info(f"@component_callback for button {ctx.custom_id} - Error: {e}")
            await ctx.send(f"Uh oh... an error occurred deleting the clip {clyppyid}:\n{str(e)}", components=[Button(style=ButtonStyle.LINK, label=f"View your clips", url='https://clyppy.io/profile/clips')])
            await send_webhook(
                title=f'{"DM" if ctx.guild is None else ctx.guild.name}, {ctx.author.username} - \'delete\' called on {clyppyid}',
                load=f"response - unexpected error: {e}",
                color=COLOR_RED,
                url=APPUSE_LOG_WEBHOOK,
                logger=self.logger
            )

            if 'Unauthorized' in str(e):
                return
            elif is_discord_uploaded:
                return

            try:
                await add_reqqed_by(data, key=os.getenv('clyppy_post_key'))
            except:
                self.logger.info(f"@component_callback for button {ctx.custom_id} - Could not re-add reqqed by for user {ctx.author.id}")
            return

        await ctx.send("The clip has been deleted." if not is_discord_uploaded else "All embeds you've requested of this clip have been deleted.")
        await send_webhook(
            title=f'{"DM" if ctx.guild is None else ctx.guild.name}, {ctx.author.username} - \'delete\' called on {clyppyid}',
            load=f"response - success"
                 f"title: {clyppyid}",
            color=COLOR_GREEN,
            url=APPUSE_LOG_WEBHOOK,
            logger=self.logger
        )

    @slash_command(name="save", description="Save Clyppy DB", scopes=[759798762171662399])
    async def save(self, ctx: SlashContext):
        await ctx.defer()
        await ctx.send("Saving DB...")
        await self.bot.guild_settings.save()
        await ctx.send("You can now safely exit.")

    @slash_command(name="vote", description="Vote on Clyppy to gain exclusive rewards!")
    async def vote(self, ctx: SlashContext):
        await self.bot.base_embedder.vote_cmd(ctx)

    @slash_command(name="tokens", description="View your VIP tokens!")
    async def tokens(self, ctx: SlashContext):
        await ctx.defer()
        await self.bot.base_embedder.tokens_cmd(ctx)

    @slash_command(name="embed", description="Embed a video link in this chat",
                   options=[SlashCommandOption(name="url",
                                               description="The YouTube, Twitch, etc. link to embed",
                                               required=True,
                                               type=OptionType.STRING)
                            ]
                   )
    async def embed(self, ctx: SlashContext, url: str):
        # trim off extra characters at start or beginning
        while url.startswith('*') or url.startswith('['):
            url = url[1:]
        while url.endswith('*') or url.endswith(']'):
            url = url[:-1]

        if not url.startswith("https://"):
            url = "https://" + url

        for p in self.bot.platform_embedders:
            if slug := p.platform.parse_clip_url(url):
                return await self.bot.base_embedder.command_embed(
                    ctx=ctx,
                    url=url,
                    platform=p.platform,
                    slug=slug
                )
        # incompatible (should never get here, since bot.base is a catch-all)
        await ctx.send("An unexpected error occurred.")
        raise Exception(f"Error in /embed - bot.base did not catch url {url}, exited returning None")

    #@slash_command(name="alerts", description="Configure Clyppy Alerts (Live Notifications, Video Uploads, etc.")
    #async def alerts(self, ctx: SlashContext):
    #    pass

    @slash_command(name="help", description="Get help using Clyppy")
    async def help(self, ctx: SlashContext):
        await ctx.defer()
        return await self.bot.base_embedder.send_help(ctx)

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
    async def settings(self, ctx: SlashContext, quickembeds: bool = None, on_error: str = None,
                       embed_buttons: str = None):
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
        await send_webhook(
            title=f'{"DM" if ctx.guild is None else ctx.guild.name} - /settings called',
            load=f'user: {ctx.user.username}\n'
                 "Successfully changed settings:\n\n"
                 f"**quickembeds**: {chosen_embed}\n"
                 f"**on_error**: {on_error}\n"
                 f"**embed_buttons**: {embed_buttons}\n\n",
            color=COLOR_GREEN,
            url=APPUSE_LOG_WEBHOOK,
            logger=self.logger
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
        await send_webhook(
            title=f'{"DM" if ctx.guild is None else ctx.guild.name} - /settings called',
            load=f'user: {ctx.user.username}\n'
                 f'**Current Settings:**\n**quickembeds**: {qe}\n{cs}\n**embed_buttons**: {es}\n\n',
            color=COLOR_GREEN,
            url=APPUSE_LOG_WEBHOOK,
            logger=self.logger
        )

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
            w = await event.guild.fetch_widget()
            await send_webhook(
                title=f'Joined new guild: {event.guild.name}',
                load=f"id - {event.guild.id}\n"
                     f"large - {event.guild.large}\n"
                     f"members - {event.guild.member_count}\n"
                     f"widget - {w}\n",
                color=COLOR_GREEN,
                logger=self.logger
            )
            await self.post_servers(len(self.bot.guilds))

    @listen()
    async def on_guild_left(self, event: GuildLeft):
        if self.ready:
            self.logger.info(f'Left guild: {event.guild.name}')
            w = await event.guild.fetch_widget()
            await send_webhook(
                title=f'Left guild: {event.guild.name}',
                load=f"id - {event.guild.id}\n"
                     f"large - {event.guild.large}\n"
                     f"members - {event.guild.member_count}\n"
                     f"widget - {w}\n",
                color=COLOR_RED,
                logger=self.logger
            )
            await self.post_servers(len(self.bot.guilds))

    @listen(InviteCreate)
    async def on_invite_create(self, event: InviteCreate):
        if self.ready:
            self.logger.info(f"New invite {event.invite.code} for {event.invite.guild_preview.name} ({event.invite.guild_preview.id})")
            await send_webhook(
                title='new invite',
                load=f"here - https://discord.gg/{event.invite.code}",
                color=COLOR_GREEN,
                url=APPUSE_LOG_WEBHOOK,
                logger=self.logger
            )

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
            await self.bot.change_presence(activity=Activity(
                type=ActivityType.STREAMING,
                name="/help",
                url="https://twitch.tv/hesmen"
            ))

            #ss = {}
            #for s in self.bot.guilds:
            #    b = s.get_member(self.bot.user.id)
            #    if b.has_permission(Permissions.MANAGE_GUILD):
            #        ss[s.name] = s.joined_at.format()
            #self.logger.info(f"MANAGE_SERVER guilds: {len(ss)}")

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
