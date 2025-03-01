import logging
import traceback
import os
from interactions import SlashContext
from typing import Tuple
import asyncio
from dataclasses import dataclass
from bot.classes import DownloadResponse, UnknownError, BaseClip
import aiohttp


POSSIBLE_TOO_LARGE = ["trim", "info", "dm"]
POSSIBLE_ON_ERRORS = ["dm", "info"]
POSSIBLE_EMBED_BUTTONS = ["all", "view", "dl", "none"]


SUPPORT_SERVER_URL = "https://discord.gg/Xts5YMUbeS"
INVITE_LINK = "https://discord.com/oauth2/authorize?client_id=1111723928604381314&permissions=182272&scope=bot%20applications.commands"
TOPGG_VOTE_LINK = "https://top.gg/bot/1111723928604381314/vote"
INFINITY_VOTE_LINK = "https://infinitybots.gg/bot/1111723928604381314/vote"
DLIST_VOTE_LINK = "https://discordbotlist.com/bots/clyppy/upvote"
BOTLISTME_VOTE_LINK = "https://botlist.me/bots/1111723928604381314/vote"
DL_SERVER_ID = os.getenv("DL_SERVER_ID")


@dataclass
class GuildType:
    id: int
    name: str
    is_dm: bool


def create_nexus_str():
    return f"\n\n**[Invite Clyppy]({INVITE_LINK}) | [Report an Issue]({SUPPORT_SERVER_URL}) | [Vote for me!]({TOPGG_VOTE_LINK})**"


class DownloadManager:
    def __init__(self, p):
        self._parent = p
        max_concurrent = os.getenv('MAX_RUNNING_AUTOEMBED_DOWNLOADS', 5)
        self._semaphore = asyncio.Semaphore(int(max_concurrent))

    async def download_clip(self, clip: BaseClip, guild_ctx: GuildType,
                            always_download=False, overwrite_on_server=False,
                            can_send_files=False) -> DownloadResponse:
        """Return the remote video file url (first, download it and upload to https://clyppy.io for kick etc)"""
        desired_filename = f'{clip.service}_{clip.clyppy_id}.mp4'
        async with self._semaphore:
            if not isinstance(clip, BaseClip):
                raise TypeError(f"Invalid clip object passed to download_clip of type {type(clip)}")
            self._parent.logger.info("Run clip.download()")
        if str(guild_ctx.id) == str(DL_SERVER_ID) or always_download:
            r = await clip.dl_download(filename=desired_filename, can_send_files=can_send_files)
            r.can_be_uploaded = False  # make sure to download and create a clyppy.io link  
        else:
            r = await clip.download(filename=desired_filename, can_send_files=can_send_files)
        if r is None:
            raise UnknownError

        if overwrite_on_server and not (r.can_be_uploaded and can_send_files):
            self._parent.logger.info(f"Uploading video for {clip.clyppy_id} ({clip.url}) to server...")
            new = await clip.upload_to_clyppyio(r)
            self._parent.logger.info(f"Overwriting video url for {clip.clyppy_id} on server with {new.remote_url}...")
            res = await clip.overwrite_mp4(new.remote_url)
            if res['code'] == 202:
                self._parent.logger.info(f"https://clyppy.io/{clip.clyppy_id} does not exist, so no overwrite was performed")
            r.filesize = new.filesize
            r.remote_url = new.remote_url
        elif overwrite_on_server and (r.can_be_uploaded and can_send_files):
            self._parent.logger.info(f"Was instructed to replace on server for {clip.id}, but skipping bc we can upload to Discord")

        return r


class Tools:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.dl = DownloadManager(self)

    async def send_error_message(self, msg_embed, dm_content, guild, ctx, bot, delete_after_on_reply=None):
        if isinstance(ctx, SlashContext):
            return
        err = ""
        if guild.id == ctx.author.id:
            pass  # don't use 'dm' setting if we're already in a dm, just reply
        elif bot.guild_settings.is_dm_on_error(guild.id):
            await self.send_dm_err_msg(ctx, guild, dm_content)
            return

        if error_channel_id := bot.guild_settings.get_error_channel(guild.id):
            if error_channel := bot.get_channel(error_channel_id):
                try:
                    await error_channel.send(embed=msg_embed)
                    return
                except Exception as e:
                    err += f"An error occurred when trying to message the channel <#{error_channel_id}>\n"
                    self.logger.warning(f"Cannot send to error channel {error_channel_id} in guild {guild.id}: {e}")
            else:
                err += (f"Could not find the channel <#{error_channel_id}>. "
                        f"Please reset the `error_channel` with `/setup`\n")

        await ctx.reply(err, embed=msg_embed, delete_after=delete_after_on_reply)

    async def send_dm_err_msg(self, ctx, guild, content):
        try:
            await ctx.author.send(f"{content}\n\n"
                                  f"This error occurred while trying to embed the clip in {guild.name}. "
                                  f"You're receiving this message because that server has the 'dm' setting "
                                  f"enabled for one of its `/settings`")
        except:
            self.logger.info(f"Failed to send DM to {ctx.author.name} ({ctx.author.id})\n{traceback.format_exc()}")
