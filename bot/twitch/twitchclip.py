from datetime import datetime, timezone
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from bot.errors import DriverDownloadFailed, ClipNotExists
from interactions import Message
import concurrent.futures
import asyncio
from typing import Union
import yt_dlp
import logging
import os


class TwitchClip:
    def __init__(self, slug):
        self.logger = logging.getLogger(__name__)
        self.service = "twitch"
        self.id, self.url = slug, f"clips.twitch.tv/{slug}"

    async def download(self, filename: Union[str, None] = None):
        if filename is None:
            filename = f'clyppy_{self.service}_{self.id}.mp4'
        self.logger.info(f"Downloading with yt-dlp: {filename}")
        ydl_opts = {
            'format': 'best',
            'outtmpl': filename,
            'quiet': True,
            'no_warnings': True,
        }

        # Download using yt-dlp
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Run download in a thread pool to avoid blocking
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: ydl.download([self.url])
                )

            if os.path.exists(filename):
                return filename

            return None
        except Exception as e:
            self.logger.error(f"yt-dlp download error: {str(e)}")
            return None
