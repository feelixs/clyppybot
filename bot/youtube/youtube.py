import logging
import yt_dlp
import asyncio
import os
import re
from bot.classes import BaseClip, BaseMisc


class YtMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "YouTube"
        self.silence_invalid_url = True

    def parse_clip_url(self, url: str) -> str:
        """
            Extracts the video ID from a YouTube URL if present.
            Works with all supported URL formats.
        """
        # Common YouTube URL patterns
        patterns = [
            r'(?:youtube\.com/(?:[^/]+/.+/|(?:v|e(?:mbed)?)/|.*[?&]v=)|youtu\.be/)([^"&?/ ]{11})',
            # Standard and embedded URLs
            r'(?:youtube\.com/shorts/)([^"&?/ ]{11})'  # Shorts URLs
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str) -> 'YtClip':
        slug = self.parse_clip_url(url)
        valid = await self.is_shortform(url)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            return None
        self.logger.info(f"{url} is_shortform=True")

        return YtClip(slug, bool(re.search(r'youtube\.com/shorts/', url)))


class YtClip(BaseClip):
    def __init__(self, slug, short):
        super().__init__(slug)
        self.service = "youtube"
        if short:
            self.url = f"https://youtube.com/shorts/{slug}"
        else:
            self.url = f"https://youtube.com/watch/?v={slug}"

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
