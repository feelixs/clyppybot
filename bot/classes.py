from abc import ABC, abstractmethod
import logging
import asyncio
import yt_dlp
import os

TARGET_SIZE_MB = 8


class BaseClip(ABC):
    """Base class for all clip types"""
    def __init__(self, slug):
        self.service = None
        self.url = None
        self.id = slug
        self.logger = logging.getLogger(__name__)

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


class BaseMisc(ABC):
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.platform_name = None
        self.silence_invalid_url = False

    @abstractmethod
    async def get_clip(self, url: str) -> 'BaseClip':
        ...

    @abstractmethod
    def parse_clip_url(self, url: str) -> str:
        ...

    def is_clip_link(self, url: str) -> bool:
        """
            Checks if a URL is a valid link format.
        """
        return bool(self.parse_clip_url(url))

    async def is_shortform(self, url: str) -> bool:
        """
            Uses yt-dlp to determine if the provided url is short-form (60 seconds or less)
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
