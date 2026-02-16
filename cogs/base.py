import asyncio
from datetime import datetime, timezone
from bot.classes import BaseMisc, send_webhook
from interactions import (Extension, Embed, slash_command, SlashContext, SlashCommandOption, OptionType, listen,
                          Permissions, Task, IntervalTrigger, ComponentContext, Message,
                          component_callback, Button, ButtonStyle, Activity, ActivityType, SlashCommandChoice)
from bot.env import SUPPORT_SERVER_URL
from bot.env import POSSIBLE_ON_ERRORS, POSSIBLE_EMBED_BUTTONS, APPUSE_LOG_WEBHOOK, VERSION, EMBED_TXT_COMMAND, is_contrib_instance, log_api_bypass
from interactions.api.events.discord import GuildJoin, GuildLeft, MessageCreate, InviteCreate
from bot.io import get_clip_info, callback_clip_delete_msg, add_reqqed_by, subtract_tokens, refresh_clip
from bot.types import COLOR_GREEN, COLOR_RED
from typing import Tuple, Optional
from re import compile
import logging
import aiohttp
import os


def format_count(count: int) -> str:
    """Format a number with commas (e.g., 1004690 -> '1,004,690')"""
    return f"{count:,} clips"


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
        self.cookie_refresh_task = Task(self.refresh_cookies_task, IntervalTrigger(seconds=60 * 60 * 6))  # refresh cookies every 6 hours
        self.status_update_task = Task(self.update_status, IntervalTrigger(seconds=60 * 5))  # update status every few minutes
        self.base_embedder = self.bot.base_embedder.embedder

    @staticmethod
    def _sanitize_url(url: str) -> str:
        # Remove Discord's url: prefix if present
        if url.startswith("url:"):
            url = url[4:]

        # trim off extra characters at start or beginning
        while url.startswith('*') or url.startswith('[') or url.startswith('`'):
            url = url[1:]
        while url.endswith('*') or url.endswith(']') or url.endswith('`'):
            url = url[:-1]
        if url.startswith("http://"):
            url = "https://" + url[7:]  # Upgrade http to https
        elif not url.startswith("https://"):
            url = "https://" + url
        return url

    def _get_first_clip_link(self, message_content: str) -> Optional[str]:
        """Extract the first valid clip link from a message"""
        words = self.base_embedder.get_words(message_content)
        for word in words:
            # Remove Discord's url: prefix if present
            if word.startswith("url:"):
                word = word[4:]
            for platform in self.bot.platform_embedders:
                if platform.embedder.platform_tools.is_clip_link(word):
                    return self._sanitize_url(word)  # Clean before returning
        return None

    @listen(MessageCreate)
    async def on_message_create(self, event: MessageCreate):
        if event.message.author.id == self.bot.user.id:
            # don't respond to bot's own messages
            return

        # check for text commands
        msg = event.message.content
        split = msg.split(' ')
        if msg.startswith(EMBED_TXT_COMMAND):
            # Check if it's ONLY ".embed" (reply-to mode)
            if msg.strip() == EMBED_TXT_COMMAND:
                # Fetch referenced message
                ref_msg = await event.message.fetch_referenced_message()
                if not ref_msg:
                    return await event.message.reply("Please reply to a message containing a clip link or use `.embed <URL>`")

                url = self._get_first_clip_link(event.message.content) or self._get_first_clip_link(ref_msg.content)
                if not url:
                    return await event.message.reply("No clip links found in either message")

                # Sanitize URL
                url = self._sanitize_url(url)
                for p in self.bot.platform_embedders:
                    if p.embedder.platform_tools.is_clip_link(url):
                        return await p.handle_message(event, skip_check=True, url=url)

                # No platform matched
                return await event.message.reply("Invalid or unsupported URL")

            # Original validation
            if len(split) <= 1:
                return await event.message.reply("Please provide a URL to embed like `.embed https://example.com`")
            # handle .embed command
            words = self.base_embedder.get_words(msg)  # Use msg instead of event.message.content
            for p in self.bot.platform_embedders:
                contains_clip_link, _ = p.embedder.get_next_clip_link_loc(
                    words=words,
                    n=0,
                    print=False
                )
                if contains_clip_link:
                    return await p.handle_message(event)

        # Check for single-word commands
        msg = msg.strip()
        if len(split) == 1:  # Only check for commands with no arguments
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

    @component_callback(compile(r"rbtn-.*"))
    async def refresh_button_response(self, ctx: ComponentContext):
        await ctx.defer(ephemeral=True)

        clip_ctx = ctx.custom_id.split("-")
        clyppyid = clip_ctx[-1]
        resp = await refresh_clip(clyppyid, ctx.author.id)
        if resp['code'] == 200:
            await ctx.send("Clip refreshed successfully. It may take a few hours before it's viewable again in Discord.")
        elif resp['code'] == 402:
            await ctx.send("Uh oh... it seems you don't have enough tokens to refresh this clip.\n"
                           f"You have: `{resp['req_tokens']}`, while this clip requires: `{resp['tokens_needed']}`")
        elif resp['code'] == 202:
            # todo -> see if we can't provide a 'no-cache' header to discord?
            await ctx.send("Uh oh... it seems the clip has already been refreshed. Please check back in a few hours.\n")
        else:
            await ctx.send("Uh oh... an error occurred while refreshing the clip.\n"
                           f"Error code: `{resp['code']}`\n"
                           f"Message: `{resp['error']}`")

    @component_callback(compile(r"ibtn-.*"))
    async def info_button_response(self, ctx: ComponentContext):
        await ctx.defer(ephemeral=True)

        clip_ctx = ctx.custom_id.split("-")
        clyppyid = clip_ctx[-1]
        is_discord_uploaded = clip_ctx[1] == "d"  # was it a discord upload

        try:
            clyppy_cdn = False

            clip_info = await get_clip_info(clyppyid, ctx_type='BotInteraction' if is_discord_uploaded else 'StoredVideo')
            self.logger.info(f"@component_callback for button {ctx.custom_id} - clip_info: {clip_info}")
            if clip_info['match']:
                clip_url = clip_info['url']

                original = clip_info['requested_by']
                if original is not None:
                    original = int(original)

                cmp_url = 'https://clyppy.io/profile/clips'
                cpm_params = f'?msgid={ctx.message.id}&clipid={clyppyid}'
                buttons = [
                    Button(
                        style=ButtonStyle.DANGER,
                        label="X",
                        custom_id=f"ibtn-delete-d-{clyppyid}" if is_discord_uploaded else f"ibtn-delete-{clyppyid}"
                    ),
                    Button(style=ButtonStyle.LINK, label=f"View your clips", url=cmp_url + cpm_params)
                ]

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
                        expires_dt = None if clip_info['expires_at'] is None else datetime.fromtimestamp(clip_info['expires_at'], tz=timezone.utc)
                        if expires_dt is not None and expires_dt > datetime.now(timezone.utc):
                            exp_str = "Expires"
                        else:
                            exp_str = "Expired"
                            buttons.pop(-1)  # remove the "View your clips" button
                            buttons.append(Button(style=ButtonStyle.BLURPLE, label="File Expired - Refresh?", custom_id=f"rbtn-{clyppyid}"))
                        embed.add_field(name=exp_str, value=f"{clip_info['expiry_ts_str']}")
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

        cmp_url = 'https://clyppy.io/profile/clips'
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
            await ctx.send(f"Uh oh... an error occurred deleting the clip {clyppyid}:\n{str(e)}", components=[Button(style=ButtonStyle.LINK, label=f"View your clips", url=cmp_url)])
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

    @component_callback(compile(r"server_rank_.*"))
    async def server_rank_button(self, ctx: ComponentContext):
        """Handle server ranking pagination button clicks."""
        await ctx.defer(edit_origin=True)

        from bot.utils.pagination import ServerRankPagination, ServerRankPaginationState
        import json
        import base64

        # Parse custom_id: server_rank_{action}_{encoded_state}
        parts = ctx.custom_id.split("_", 3)
        action = parts[2]  # first, prev, next, last
        encoded_state = parts[3]

        # Decode state
        state_json = base64.b64decode(encoded_state).decode('utf-8')
        state_dict = json.loads(state_json)
        state = ServerRankPaginationState(**state_dict)

        # Calculate new page
        if action == "first":
            new_page = 1
        elif action == "prev":
            new_page = max(1, state.page - 1)
        elif action == "next":
            new_page = min(state.total_pages, state.page + 1)
        elif action == "last":
            new_page = state.total_pages
        else:
            return  # Invalid action

        # Fetch new page data
        data = await ServerRankPagination.fetch_ranking_data(
            guild_id=state.guild_id,
            page=new_page,
            time_period=state.time_period
        )

        if not data["success"]:
            await ctx.send("Failed to load page. Please try again.", ephemeral=True)
            return

        # Update state
        state.page = new_page

        # Create new embed and buttons
        embed = ServerRankPagination.create_embed(
            ranking_data=data["data"],
            page=new_page,
            total_pages=state.total_pages,
            guild_id=state.guild_id,
            entries_per_page=state.entries_per_page
        )

        buttons = ServerRankPagination.create_buttons(
            page=new_page,
            total_pages=state.total_pages,
            state=state
        )

        # Update message
        await ctx.edit_origin(embed=embed, components=buttons)

    @component_callback(compile(r"ur_.*"))
    async def user_rank_button(self, ctx: ComponentContext):
        """Handle user ranking pagination button clicks."""
        await ctx.defer(edit_origin=True)

        from bot.utils.pagination import UserRankPagination, UserRankPaginationState

        # Parse compact custom_id: ur_{action}_{user_id}_{tp}_{page}_{total}_{bots}_{ts}
        parts = ctx.custom_id.split("_")
        action = parts[1]  # f, p, n, l
        user_id = parts[2]
        tp_code = parts[3]
        current_page = int(parts[4])
        total_pages = int(parts[5])
        include_bots = parts[6] == "1"

        # Decode time period
        time_period = {"a": "all", "w": "week", "m": "month", "t": "today"}.get(tp_code, "all")
        requester_id = str(ctx.author.id)

        # Calculate new page
        if action == "f":
            new_page = 1
        elif action == "p":
            new_page = max(1, current_page - 1)
        elif action == "n":
            new_page = min(total_pages, current_page + 1)
        elif action == "l":
            new_page = total_pages
        else:
            return

        # Fetch new page data
        data = await UserRankPagination.fetch_ranking_data(page=new_page, time_period=time_period, requester_id=requester_id, include_bots=include_bots)

        if not data.get("success"):
            await ctx.send("Failed to load page. Please try again.", ephemeral=True)
            return

        # Create state for buttons
        state = UserRankPaginationState(
            user_id=user_id,
            time_period=time_period,
            page=new_page,
            total_pages=total_pages,
            include_bots=include_bots
        )

        # Create new embed and buttons
        embed = UserRankPagination.create_embed(
            ranking_data=data["data"],
            page=new_page,
            total_pages=total_pages,
            user_id=user_id,
            time_period=time_period,
            top_user=data.get("top_user")
        )

        buttons = UserRankPagination.create_buttons(
            page=new_page,
            total_pages=total_pages,
            state=state
        )

        # Update message
        await ctx.edit_origin(embed=embed, components=buttons)

    @slash_command(name="setquickembeds", scopes=[759798762171662399], options=[
        SlashCommandOption(name="guild_id", type=OptionType.STRING, required=True),
        SlashCommandOption(name="value", type=OptionType.STRING, required=True,
                           description="Platforms: 'all', 'none', or comma-separated (e.g., 'twitch,kick')")])
    async def setquickembeds(self, ctx, guild_id: str, value: str):
        success, error_msg, valid_platforms = self.bot.guild_settings.set_quickembed_platforms(int(guild_id), value)
        if success:
            return await ctx.send(f"OK! Set quickembeds to: {valid_platforms if valid_platforms else 'none'}")
        else:
            return await ctx.send(f"Error: {error_msg}")

    @slash_command(name="change_tokens", scopes=[759798762171662399], options=[
        SlashCommandOption(name="user_id", type=OptionType.STRING, required=True),
        SlashCommandOption(name="value", type=OptionType.INTEGER, required=True),
        SlashCommandOption(name="add", type=OptionType.BOOLEAN, required=False)
    ])
    async def change_tokens(self, ctx, user_id: int, value: int, add=True):
        try:
            u = await self.bot.fetch_user(user_id)
        except Exception as e:
            await ctx.send(f"Error while fetching user {user_id}: {e}")
            return

        if add:
            value *= -1  # because the api endpoint is for subtraction
        try:
            s = await subtract_tokens(u, value, reason='Token Adjustment')
            await ctx.send(f"The change returned {s}")
        except Exception as e:
            await ctx.send(str(e))

    @slash_command(name="save", description="Save Clyppy DB", scopes=[759798762171662399])
    async def save(self, ctx: SlashContext):
        await ctx.defer()
        await ctx.send("Saving DB...")
        await self.bot.guild_settings.save()
        await self.post_servers(len(self.bot.guilds))
        await ctx.send("You can now safely exit.")

    @slash_command(name="viewsettings", description="View settings for a guild", scopes=[759798762171662399], options=[
        SlashCommandOption(name="guild_id", type=OptionType.STRING, required=True, description="Guild ID to view")])
    async def viewsettings(self, ctx: SlashContext, guild_id: str):
        await ctx.defer()

        try:
            gid = int(guild_id)
        except ValueError:
            await ctx.send("Invalid guild ID.")
            return

        # Fetch all settings
        quickembeds, qe_is_default = self.bot.guild_settings.get_quickembed_platforms(gid)
        error_channel = self.bot.guild_settings.get_error_channel(gid)
        embed_buttons = self.bot.guild_settings.get_embed_buttons(gid)
        on_error = self.bot.guild_settings.get_on_error(gid)
        nsfw_enabled = self.bot.guild_settings.get_nsfw_enabled(gid)

        # Format response
        embed = Embed(
            title=f"Settings for Guild {gid}",
            color=COLOR_GREEN
        )
        s = ", ".join(quickembeds) if quickembeds else "None"
        embed.add_field(name="QuickEmbed Platforms", value=f'{s} (default)' if qe_is_default else s, inline=False)
        embed.add_field(name="Error Channel", value=f"<#{error_channel}>" if error_channel else "Not set", inline=True)
        embed.add_field(name="Embed Buttons", value=POSSIBLE_EMBED_BUTTONS[embed_buttons], inline=True)
        embed.add_field(name="On Error", value=str(on_error), inline=True)
        embed.add_field(name="NSFW Enabled", value="Yes" if nsfw_enabled else "No", inline=True)

        await ctx.send(embed=embed)

    @slash_command(
        name="refresh_cookies",
        description="Manually refresh cookies from server",
        scopes=[759798762171662399],
        options=[
            SlashCommandOption(
                name="confirm",
                description="Type 'yes' to confirm",
                type=OptionType.STRING,
                required=True
            )
        ]
    )
    async def refresh_cookies_cmd(self, ctx: SlashContext, confirm: str):
        if confirm.lower() != 'yes':
            await ctx.send("Cancelled.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)
        await self.refresh_cookies_task()
        await ctx.send("✅ Cookies refreshed from server!", ephemeral=True)

    @slash_command(
        name="delete_message",
        description="Manually delete a message sent by Clyppy",
        scopes=[759798762171662399],
        options=[
            SlashCommandOption(
                name="message_id",
                description="The ID of the message to delete",
                type=OptionType.STRING,
                required=True
            ),
            SlashCommandOption(
                name="channel_id",
                description="The ID of the channel (or user ID if is_dm is True)",
                type=OptionType.STRING,
                required=True
            ),
            SlashCommandOption(
                name="is_dm",
                description="If True, channel_id is treated as a user ID to fetch their DM",
                type=OptionType.BOOLEAN,
                required=False
            )
        ]
    )
    async def delete_msg_cmd(self, ctx: SlashContext, message_id: str, channel_id: str, is_dm: bool = False):
        await ctx.defer(ephemeral=True)

        # Only allow specific user to use this command
        if ctx.author.id != 164115540426752001:
            await ctx.send("You are not authorized to use this command.")
            return

        try:
            if is_dm:
                user = await self.bot.fetch_user(int(channel_id))
                channel = await user.fetch_dm(force=False)
            else:
                channel = await self.bot.fetch_channel(int(channel_id))
            message = await channel.fetch_message(int(message_id))
            await message.delete()
            await ctx.send(f"Successfully deleted message {message_id} from {'DM with user ' if is_dm else 'channel '}{channel_id}")
        except Exception as e:
            await ctx.send(f"Error deleting message: {e}")

    @slash_command(name="vote", description="Vote on Clyppy to gain exclusive rewards!")
    async def vote(self, ctx: SlashContext):
        await self.bot.base_embedder.vote_cmd(ctx)

    @slash_command(name="tokens", description="View your VIP tokens!")
    async def tokens(self, ctx: SlashContext):
        await ctx.defer()
        await self.bot.base_embedder.tokens_cmd(ctx)

    @slash_command(name="myclips", description="View your personal clip library")
    async def myclips(self, ctx: SlashContext):
        await self.bot.base_embedder.myclips_cmd(ctx)

    @slash_command(name="invite", description="Display a link to invite Clyppy to your server")
    async def invite(self, ctx: SlashContext):
        await self.bot.base_embedder.invite_cmd(ctx)

    @slash_command(name="profile",
                   sub_cmd_name="info",
                   sub_cmd_description="View your Clyppy profile",
                   options=[SlashCommandOption(
                       name="user",
                       description="User ID or username",
                       required=False,
                       type=OptionType.STRING)
                   ])
    async def profile(self, ctx: SlashContext, user: str = None):
        await self.bot.base_embedder.profile_cmd(ctx, user)

    @slash_command(name="profile",
                   sub_cmd_name="rank",
                   sub_cmd_description="View your ranking in clip embeds",
                   options=[
                       SlashCommandOption(
                           name="user",
                           description="User ID or username (defaults to yourself)",
                           required=False,
                           type=OptionType.STRING
                       ),
                       SlashCommandOption(
                           name="time_period",
                           description="Time period for ranking",
                           required=False,
                           type=OptionType.STRING,
                           choices=[
                               SlashCommandChoice(name="All Time", value="all"),
                               SlashCommandChoice(name="This Week", value="week"),
                               SlashCommandChoice(name="This Month", value="month"),
                               SlashCommandChoice(name="Today", value="today"),
                           ]
                       ),
                       SlashCommandOption(
                           name="bots",
                           description="Include bots in rankings (default: No)",
                           required=False,
                           type=OptionType.BOOLEAN
                       )
                   ])
    async def profile_rank(self, ctx: SlashContext, user: str = None, time_period: str = "all", bots: bool = False):
        await self.bot.base_embedder.profile_rank_cmd(ctx, user, time_period, bots)

    # todo add command that just fetches the cost to embed a specific video without uploading/embedding it
    # i'll have to fetch its duration/download it to check duration
    #@slash_command(name=)

    @slash_command(name="embed", description="Embed a video link in this chat",
                   options=[SlashCommandOption(
                       name="url",
                       description="The YouTube, Twitch, etc. link to embed",
                       required=True,
                       type=OptionType.STRING)
                   ])
    async def embed(self, ctx: SlashContext, url: str):
        # Defer IMMEDIATELY before any processing to ensure we respond within 3s
        await ctx.defer()

        self.logger.info(f"@slash_command for /embed - {ctx.author.id} - {url}")
        url = self._sanitize_url(url)

        # Check if bot is shutting down
        if self.bot.is_shutting_down:
            self.logger.info(f"Bot is shutting down, queueing /embed command for {url}")

            try:
                # Interaction already deferred at the top of this function

                from bot.task_queue import SlashCommandTask
                task = SlashCommandTask(
                    interaction_id=int(ctx.id),
                    interaction_token=ctx.token,
                    channel_id=int(ctx.channel_id),
                    channel_name=ctx.channel.name if hasattr(ctx.channel, 'name') else 'unknown-channel',
                    guild_id=int(ctx.guild_id) if ctx.guild else None,
                    guild_name=ctx.guild.name if ctx.guild else None,
                    user_id=int(ctx.author.id),
                    user_username=ctx.author.username,
                    clip_url=url,
                    extend_with_ai=False
                )
                self.bot.task_queue.add_slash_command(task)
                self.logger.info(f"Successfully queued task for {url}")
            except Exception as e:
                self.logger.error(f"Failed to queue task during shutdown: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
            # Don't send any response - the deferred state will be resumed on restart
            return

        for p in self.bot.platform_embedders:
            if slug := p.platform.parse_clip_url(url):
                await self.bot.base_embedder.command_embed(
                    ctx=ctx,
                    already_deferred=True,
                    url=url,
                    platform=p.platform,
                    slug=slug
                )
                return
        # incompatible (should never get here, since bot.base is a catch-all)
        await ctx.send("An unexpected error occurred.")
        raise Exception(f"Error in /embed - bot.base did not catch url {url}, exited returning None")

    #@slash_command(name="ai_extend", description="Extend a video with AI",
    #               options=[SlashCommandOption(
    #                   name="url",
    #                   description="The YouTube, Twitch, etc. link to extend",
    #                   required=True,
    #                   type=OptionType.STRING)
    #               ])
    #async def ai_extend(self, ctx: SlashContext, url: str):
    #    self.logger.info(f"@slash_command for /extend - {ctx.author.id} - {url}")
    #    url = self._sanitize_url(url)
    #    for p in self.bot.platform_embedders:
    #        if slug := p.platform.parse_clip_url(url):
    #            return await self.bot.base_embedder.command_embed(
    #                ctx=ctx,
    #                url=url,
    #                platform=p.platform,
    #                slug=slug,
    #                extend_with_ai=True
    #            )
    #    # incompatible (should never get here, since bot.base is a catch-all)
    #    await ctx.send("An unexpected error occurred.")
    #    raise Exception(f"Error in /extend - bot.base did not catch url {url}, exited returning None")

    @slash_command(name="help", description="Get help using Clyppy")
    async def help(self, ctx: SlashContext):
        await ctx.defer()
        await self.bot.base_embedder.send_help(ctx)

    @slash_command(name="setup", description="Display or change Clyppy's general settings",
                   options=[SlashCommandOption(name="error_channel", type=OptionType.CHANNEL,
                                               description="The channel where Clyppy should send error messages",
                                               required=False)])
    async def setup(self, ctx: SlashContext, error_channel=None):
        if ctx.guild is None:
            asyncio.create_task(ctx.send("This command is only available in servers."))
            return
        if ctx.guild.id == ctx.author.id:  # in case they patch the "dm guild is None" situation
            asyncio.create_task(ctx.send("This command is only available in servers."))
            return

        if not ctx.author.has_permission(Permissions.ADMINISTRATOR):
            asyncio.create_task(ctx.send("Only members with the **Administrator** permission can change Clyppy's settings."))
            return
        if error_channel is None:
            if (ec := self.bot.guild_settings.get_error_channel(ctx.guild.id)) == 0:
                cur_chn = ("Unconfigured\n\n"
                           "When not configured, Clyppy will send error messages to the same channel as the interaction.")
                asyncio.create_task(ctx.send("Current error channel: " + cur_chn))
                return
            else:
                try:
                    cur_chn = self.bot.get_channel(ec)
                    asyncio.create_task(ctx.send(f"Current error channel: {cur_chn.mention}"))
                    return
                except:
                    cur_chn = ("Channel not found - error channel was reset to **Unconfigured**\n\n"
                               "Make sure Clyppy has the `VIEW_CHANNELS` permission, and that the channel still exists."
                               "\nWhen not configured, Clyppy will send error messages to the same channel as the interaction.\n\n"
                               f"More info:\nTried to retrieve channel <#{ec}> but failed.")
                    self.bot.guild_settings.set_error_channel(ctx.guild.id, 0)
                    asyncio.create_task(ctx.send("Current error channel: " + cur_chn))
                    return

        await ctx.defer()
        if ctx.guild is None:
            asyncio.create_task(ctx.send("This command is only available in servers."))
            return

        if (e := self.bot.get_channel(error_channel)) is None:
            asyncio.create_task(ctx.send(f"Channel #{error_channel} not found.\n\n"
                                  f"Please make sure Clyppy has the `VIEW_CHANNELS` permission & try again."))
            return

        res = self.bot.guild_settings.set_error_channel(ctx.guild.id, e.id)
        if res:
            asyncio.create_task(ctx.send(f"Success! Error channel set to {e.mention}"))
        else:
            asyncio.create_task(ctx.send("An error occurred while setting the error channel. Please try again."))

    @slash_command(name="settings", description="Display or change Clyppy's miscellaneous settings",
                   options=[SlashCommandOption(name="quickembeds", type=OptionType.STRING,
                                               description="Platforms: 'all', 'none', 'reset', or comma-separated (e.g., 'twitch,kick')",
                                               required=False),
                            SlashCommandOption(name="channel", type=OptionType.CHANNEL,
                                               description="Apply quickembeds to specific channel (blank = server-wide)",
                                               required=False),
                            SlashCommandOption(name="on_error", type=OptionType.STRING,
                                               description="Choose what Clyppy should do upon error",
                                               required=False),
                            SlashCommandOption(name="embed_buttons", type=OptionType.STRING,
                                               description="Configure what buttons Clyppy shows when embedding clips",
                                               required=False)
                            ])
    async def settings(self, ctx: SlashContext, quickembeds: str = None, channel = None,
                       on_error: str = None, embed_buttons: str = None):
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

        channel_id = channel.id if channel else None
        current_qe_platforms, qe_is_default = self.bot.guild_settings.get_quickembed_platforms(ctx.guild.id, channel_id)
        chosen_qe = current_qe_platforms
        qe_scope = f"in {channel.mention}" if channel else "server-wide"

        if quickembeds is not None:
            # Handle reset command to remove channel override
            if quickembeds.lower() == 'reset':
                if channel_id is None:
                    await ctx.send("Cannot reset server-wide settings. Use `quickembeds=none` to disable all platforms.")
                    return
                success = self.bot.guild_settings.delete_channel_quickembed_setting(ctx.guild.id, channel_id)
                if success:
                    await ctx.send(f"Channel override removed for {channel.mention}. Now using server-wide settings.")
                else:
                    await ctx.send("Error removing channel override.")
                return

            success, error_msg, valid_platforms = self.bot.guild_settings.set_quickembed_platforms(
                ctx.guild.id, quickembeds, channel_id)
            if not success:
                await ctx.send(f"Error setting quickembeds: {error_msg}")
                return
            chosen_qe = valid_platforms

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

        # Format quickembed display
        from bot.db import VALID_QUICKEMBED_PLATFORMS
        if not chosen_qe:
            qe_display = "none"
        elif set(chosen_qe) == set(VALID_QUICKEMBED_PLATFORMS):
            qe_display = "all"
        else:
            qe_display = ', '.join(chosen_qe)

        qe_scope_msg = f" ({qe_scope})" if quickembeds is not None else ""
        await ctx.send(
            "Successfully changed settings:\n\n"
            f"**quickembeds**: {qe_display}{' (default)' if qe_is_default else ''}{qe_scope_msg}\n"
            f"**on_error**: {on_error}\n"
            f"**embed_buttons**: {embed_buttons}\n\n"
        )
        await send_webhook(
            title=f'{"DM" if ctx.guild is None else ctx.guild.name} - /settings called',
            load=f'user: {ctx.user.username}\n'
                 "Successfully changed settings:\n\n"
                 f"**quickembeds**: {qe_display}\n"
                 f"**on_error**: {on_error}\n"
                 f"**embed_buttons**: {embed_buttons}\n\n",
            color=COLOR_GREEN,
            url=APPUSE_LOG_WEBHOOK,
            logger=self.logger
        )

    async def _send_settings_help(self, ctx: SlashContext, prepend_admin: bool = False):
        from bot.db import VALID_QUICKEMBED_PLATFORMS, PLATFORM_NAME_TO_ID
        cs = self.bot.guild_settings.get_setting_str(ctx.guild.id)
        es = self.bot.guild_settings.get_embed_buttons(ctx.guild.id)
        qe_platforms, qe_is_default = self.bot.guild_settings.get_quickembed_platforms(ctx.guild.id)

        es = POSSIBLE_EMBED_BUTTONS[es]

        # Format quickembed display
        if not qe_platforms:
            qe = "none"
        elif set(qe_platforms) == set(VALID_QUICKEMBED_PLATFORMS):
            qe = "all"
        else:
            qe = ', '.join(qe_platforms)

        # Use friendly platform names for display
        valid_platforms_str = ', '.join(PLATFORM_NAME_TO_ID.keys())

        # Build channel overrides section
        overrides = self.bot.guild_settings.list_channel_overrides(ctx.guild.id)
        channel_overrides_section = ""
        if overrides:
            override_lines = []
            for channel_id, setting in overrides:
                try:
                    channel_obj = self.bot.get_channel(channel_id)
                    channel_name = channel_obj.mention if channel_obj else f"<#{channel_id}>"
                    # Parse setting for display
                    if setting == 'none':
                        platforms = 'none'
                    elif setting == 'all':
                        platforms = 'all'
                    else:
                        platforms = ', '.join(setting.split(','))
                    override_lines.append(f"  {channel_name}: {platforms}")
                except Exception:
                    pass
            if override_lines:
                channel_overrides_section = "\n\n**Channel Overrides:**\n" + "\n".join(override_lines)

        about = (
            '**Configurable Settings:**\n'
            'Below are the settings you can configure using this command. Each setting name is in **bold** '
            'followed by its available options.\n\n'
            '**quickembeds** Configure which platforms Clyppy automatically embeds:\n'
            ' - `all`: Enable for all platforms\n'
            ' - `none`: Disable all quickembeds (use `/embed` command instead)\n'
            ' - `reset`: Remove channel-specific override (use with `channel` parameter)\n'
            f' - Comma-separated list: e.g., `Twitch,Kick,Medal`\n'
            f' - Valid platforms: `None, All, {valid_platforms_str}`\n'
            ' - Use `channel` parameter to apply to specific channel (blank = server-wide)\n\n'
            '**on_error** Choose what Clyppy does when it encounters an error:\n'
            ' - `info`: Respond to the message with the error.\n'
            ' - `dm`: DM the message author about the error.\n\n'
            '**embed_buttons** Choose which buttons Clyppy shows under embedded videos:\n'
            ' - `none`: No buttons, just the video.\n'
            ' - `view`: A button to the original clip.\n'
            ' - `dl`: A button to download the original video file (on compatible clips).\n'
            ' - `all`: Shows all available buttons.\n\n'
            f'**Current Settings:**\n**quickembeds** (server-wide): {qe}{" (default)" if qe_is_default else ""}'
            f'{channel_overrides_section}\n{cs}\n**embed_buttons**: {es}\n\n'
            f'Something missing? Please **[Suggest a Feature]({SUPPORT_SERVER_URL})**'
        )

        if prepend_admin:
            about = "**ONLY MEMBERS WITH THE ADMINISTRATOR PERMISSIONS CAN EDIT SETTINGS**\n\n" + about

        tutorial_embed = Embed(title="CLYPPY SETTINGS", description=about)
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

        self.logger.info("Saving database to the server...")
        await self.bot.guild_settings.save()

    async def refresh_cookies_task(self):
        """Download cookies from felixcreations.com every 24 hours"""
        if not self.ready:
            self.logger.info("Bot not ready, skipping cookie refresh task")
            return

        if is_contrib_instance(self.logger):
            log_api_bypass(self.logger, "https://felixcreations.com/api/cookies/get", "GET")
            self.logger.info("[CONTRIB MODE] Cookie refresh bypassed")
            return

        self.logger.info("Downloading cookies from server...")

        # Check if API key is available
        api_key = os.getenv('clyppy_post_key')
        if not api_key:
            self.logger.warning("Cookie refresh skipped: clyppy_post_key not set")
            return

        try:
            async with aiohttp.ClientSession() as session:
                url = "https://felixcreations.com/api/cookies/get"
                headers = {'X-API-Key': api_key}

                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        cookies_content = await response.text()
                        cookie_file_path = os.getenv('COOKIE_FILE', '/tmp/cookies.txt')

                        with open(cookie_file_path, 'w') as f:
                            f.write(cookies_content)

                        self.logger.info(f"Successfully updated cookies at {cookie_file_path}")
                    else:
                        self.logger.warning(f"Failed to download cookies: HTTP {response.status}")
        except Exception as e:
            self.logger.error(f"Error downloading cookies: {e}")

    @listen()
    async def on_guild_join(self, event: GuildJoin):
        if self.ready:
            self.logger.info(f'Joined new guild: {event.guild.name}')
            try:
                w = await event.guild.fetch_widget()
            except:
                w = None
            await send_webhook(
                title=f'Joined new guild: {event.guild.name}',
                load=f"id - {event.guild.id}\n"
                     f"large - {event.guild.large}\n"
                     f"members - {event.guild.member_count}\n"
                     f"widget - {w}\n",
                color=COLOR_GREEN,
                logger=self.logger,
                embed=False
            )
            await self.post_servers(len(self.bot.guilds))

    @listen()
    async def on_guild_left(self, event: GuildLeft):
        if self.ready:
            self.logger.info(f'Left guild: {event.guild.name}')
            try:
                w = await event.guild.fetch_widget()
            except:
                w = None
            await send_webhook(
                title=f'Left guild: {event.guild.name}',
                load=f"id - {event.guild.id}\n"
                     f"large - {event.guild.large}\n"
                     f"members - {event.guild.member_count}\n"
                     f"widget - {w}\n",
                color=COLOR_RED,
                logger=self.logger,
                embed=False
            )
            await self.post_servers(len(self.bot.guilds))

    @listen()
    async def on_ready(self):
        if not self.ready:
            self.ready = True
            self.save_task.start()
            self.cookie_refresh_task.start()
            self.status_update_task.start()
            # Download cookies immediately on startup
            await self.refresh_cookies_task()
            self.logger.info(f"bot logged in as {self.bot.user.username}")
            self.logger.info(f"total shards: {len(self.bot.shards)}")
            self.logger.info(f"my guilds: {len(self.bot.guilds)}")
            self.logger.info(f"CLYPPY VERSION: {VERSION}")
            if os.getenv("TEST") is not None:
                await self.post_servers(len(self.bot.guilds))

            # Process queued tasks from previous session
            from bot.task_queue import process_queued_tasks
            try:
                await process_queued_tasks(self.bot, self.bot.task_queue)
            except Exception as e:
                self.logger.error(f"Error processing queued tasks: {e}")
            self.logger.info("--------------")

    async def update_status(self):
        """Fetch embed count and update bot status"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://clyppy.io/api/stats/embeds-count/") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        count = data.get("count", 0)
                        self.bot.cached_embed_count = count
                        status_text = format_count(count)
                        await self.bot.change_presence(activity=Activity(name=status_text, type=ActivityType.PLAYING))
                        self.logger.info(f"Updated status: {status_text}")
        except Exception as e:
            self.logger.warning(f"Failed to fetch embed count: {e}")

    async def post_servers(self, num: int):
        if os.getenv("TEST") is not None:
            return

        # Calculate total user count across all guilds
        total_users = sum(guild.member_count or 0 for guild in self.bot.guilds)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        url="https://top.gg/api/bots/1111723928604381314/stats", json={
                            'server_count': num,
                            'shard_count': self.bot.total_shards
                        },
                        headers={'Authorization': os.getenv('GG_TOKEN')}
                ) as resp:
                    r = await resp.text()
                    self.logger.info(f"Successfully posted servers to topp.gg - response: {r}")
        except Exception as e:
            self.logger.info(f"Failed to post servers to top.gg: {type(e).__name__}: {str(e)}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        url="https://api.botlist.me/api/v1/bots/1111723928604381314/stats",
                        json={
                            'server_count': str(num),
                            'shard_count': self.bot.total_shards
                        },
                        headers={'authorization': os.getenv('BOTLISTME_TOKEN')}
                ) as resp:
                    r = await resp.json()
                    self.logger.info(f"Successfully posted servers to botlist.me - response: {r}")
        except Exception as e:
            self.logger.info(f"Failed to post servers to botlist.me: {type(e).__name__}: {str(e)}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        url="https://discordbotlist.com/api/v1/bots/1111723928604381314/stats",
                        json={
                            'users': total_users,
                            'guilds': num
                        },
                        headers={
                            'Authorization': os.getenv('DISCORDBOTLIST_TOKEN'),
                            'Accept': 'application/json'
                        }
                ) as resp:
                    r = await resp.json()
                    self.logger.info(f"Successfully posted servers to discordbotlist.com - response: {r}")
        except Exception as e:
            self.logger.info(f"Failed to post servers to discordbotlist.com: {type(e).__name__}: {str(e)}")
