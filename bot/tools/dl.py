from bot.tools.misc import GuildType
from bot.types import DownloadResponse
from bot.errors import UnknownError
from bot.classes import BaseClip
from bot.env import DL_SERVER_ID
import asyncio
import os


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
