from abc import ABC, abstractmethod
import logging
import asyncio
import os
from yt_dlp import YoutubeDL
from typing import Tuple, Optional


TARGET_SIZE_MB = 8


class BaseClip(ABC):
    """Base class for all clip types"""

    def __init__(self, slug: str):
        self.service = None
        self.url = None
        self.id = slug
        self.logger = logging.getLogger(__name__)

    async def download(self, filename=None, dlp_format='best[ext=mp4]') -> Optional[Tuple[str, float]]:
        """
        Gets direct media URL and duration from the clip URL without downloading.
        Returns tuple of (direct_url, duration_in_seconds) or None if extraction fails.
        """
        ydl_opts = {
            'format': dlp_format,  # Prefer MP4 format
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Don't download playlists
        }

        try:
            # Run extraction in a thread pool to avoid blocking
            return await asyncio.get_event_loop().run_in_executor(
                None,
                self._extract_info,
                ydl_opts
            )
        except Exception as e:
            self.logger.error(f"Failed to get direct URL: {str(e)}")
            return None

    def _extract_info(self, ydl_opts: dict) -> Tuple[str, float]:
        """
        Helper method to extract URL and duration information using yt-dlp.
        Runs in thread pool to avoid blocking the event loop.
        """
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(self.url, download=False)
            if not info:
                raise ValueError("Could not extract video information")
            # Get duration
            duration = info.get('duration', 0)

            # Get direct URL
            if 'url' in info:
                return info['url'], duration
            elif 'formats' in info and info['formats']:
                # Get best MP4 format
                mp4_formats = [f for f in info['formats'] if f.get('ext') == 'mp4']
                if mp4_formats:
                    # Sort by quality (typically bitrate or filesize)
                    best_format = sorted(
                        mp4_formats,
                        key=lambda x: x.get('filesize', 0) or x.get('tbr', 0),
                        reverse=True
                    )[0]
                    return best_format['url'], duration

            raise ValueError("No suitable URL found in video info")


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

    async def get_len(self, url: str) -> Optional[float]:
        """
            Uses yt-dlp to check video length of the provided url
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Only extract metadata, don't download
        }

        try:
            # Run yt-dlp in an executor to avoid blocking
            def get_duration():
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return info.get('duration', 0)

            duration = await asyncio.get_event_loop().run_in_executor(
                None, get_duration
            )
            return duration

        except Exception as e:
            self.logger.error(f"Error checking video length for {url}: {str(e)}")
            return None

    async def is_shortform(self, url: str) -> bool:
        d = await self.get_len(url)
        if d is None:
            return False
        return d <= 60
