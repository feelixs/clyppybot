import undetected_chromedriver as uc
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import logging
import asyncio
import json
import time
import yt_dlp
import os


class MedalClip:
    def __init__(self, slug):
        self.id = slug
        self.service = "medal"
        self.url = f"https://medal.tv/clips/{slug}"
        self.logger = logging.getLogger(__name__)

    async def download(self, filename: str = None):
        self.logger("Downloading with yt-dlp")
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

            # Find the downloaded file
            for ext in ['mp4', 'webm']:
                filename = f'clyppy_{self.service}_{self.id}.{ext}'
                if os.path.exists(filename):
                    return filename

            return None
        except Exception as e:
            self.logger.error(f"yt-dlp download error: {str(e)}")
            return None
