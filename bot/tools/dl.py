from bot.types import DownloadResponse, LocalFileInfo
from bot.errors import UnknownError
from bot.classes import BaseClip
from typing import Union
import asyncio
import os


class DownloadManager:
    def __init__(self, p):
        self._parent = p
        max_concurrent = os.getenv('MAX_RUNNING_AUTOEMBED_DOWNLOADS', 5)
        self._semaphore = asyncio.Semaphore(int(max_concurrent))

    async def download_clip(self, clip: BaseClip, can_send_files=False, skip_upload=False) -> Union[DownloadResponse, LocalFileInfo]:
        desired_filename = f'{clip.service}_{clip.clyppy_id}.mp4' if clip.service != 'base' else f'{clip.clyppy_id}.mp4'
        async with self._semaphore:
            if not isinstance(clip, BaseClip):
                raise TypeError(f"Invalid clip object passed to download_clip of type {type(clip)}")
            self._parent.logger.info("Run clip.download()")
        if not skip_upload:
            r = await clip.download(filename=desired_filename, can_send_files=can_send_files)
        else:
            # force manual override of auto-upload (download() may upload, but dl_download() doesn't)
            r = await clip.dl_download(filename=desired_filename, can_send_files=can_send_files)
        if r is None:
            raise UnknownError
        return r
