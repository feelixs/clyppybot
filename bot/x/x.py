import logging
import yt_dlp
import asyncio
import os
import re
from bot.classes import BaseClip


class Xmisc:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.platform_name = "Twitter"
        self.silence_invalid_url = True

    @staticmethod
    def parse_clip_url(url: str) -> str:
        """
        Extracts the tweet ID/slug from various Twitter URL formats.
        Returns None if the URL is not a valid Twitter URL.
        """
        patterns = [
            r'twitter\.com/\w+/status/(\d+)',
            r'x\.com/\w+/status/(\d+)',
            r't\.co/(\w+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def is_clip_link(self, url: str) -> bool:
        """
            Checks if a URL is a valid Twitter link format.
        """
        return bool(self.parse_clip_url(url))

    async def is_shortform(self, url: str) -> bool:
        """
            Uses yt-dlp to determine if the provided Twitter url is short-form (60 seconds or less)
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Only extract metadata, don't download
        }

        try:
            # Run yt-dlp in an executor to avoid blocking
            def get_duration():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return info.get('duration', 0)

            duration = await asyncio.get_event_loop().run_in_executor(
                None, get_duration
            )

            # Check if duration is 60 seconds or less
            return duration <= 60

        except Exception as e:
            self.logger.error(f"Error checking video length for {url}: {str(e)}")
            return False

    async def get_clip(self, url: str) -> 'Xclip':
        slug = self.parse_clip_url(url)
        valid = await self.is_shortform(url)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            return None
        self.logger.info(f"{url} is_shortform=True")

        return Xclip(slug)


class Xclip(BaseClip):
    def __init__(self, slug):
        super().__init__(slug)
        self.service = "twitter"
        self.url = f"https://x.com/VideoCardz/status/{slug}"

    async def download(self, filename: str):
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
            self.logger.info(f"Could not find file")
            return None
        except Exception as e:
            self.logger.error(f"yt-dlp download error: {str(e)}")
            return None
