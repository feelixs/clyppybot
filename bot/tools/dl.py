from bot.types import DownloadResponse
from bot.errors import UnknownError
from bot.classes import BaseClip
import asyncio
import os


class DownloadManager:
    def __init__(self, p):
        self._parent = p
        max_concurrent = os.getenv('MAX_RUNNING_AUTOEMBED_DOWNLOADS', 5)
        self._semaphore = asyncio.Semaphore(int(max_concurrent))

    async def download_clip(self, clip: BaseClip, can_send_files=False) -> DownloadResponse:
        """Return the remote video file url (first, download it and upload to https://clyppy.io for kick etc)"""
        desired_filename = f'{clip.service}_{clip.clyppy_id}.mp4' if clip.service != 'base' else f'{clip.clyppy_id}.mp4'
        async with self._semaphore:
            if not isinstance(clip, BaseClip):
                raise TypeError(f"Invalid clip object passed to download_clip of type {type(clip)}")
            self._parent.logger.info("Run clip.download()")
        r = await clip.download(filename=desired_filename, can_send_files=can_send_files)
        if r is None:
            raise UnknownError
        return r
