from abc import ABC, abstractmethod
import logging
import asyncio
import os
from yt_dlp import YoutubeDL
from typing import Tuple, Optional
from dataclasses import dataclass
import base64
import aiohttp
import hashlib

TARGET_SIZE_MB = 8


@dataclass
class DownloadResponse:
    remote_url: Optional[str]
    local_file_path: Optional[str]
    duration: float


async def upload_video(video_file_path):
    # Read and encode the file
    with open(video_file_path, 'rb') as f:
        file_data = base64.b64encode(f.read()).decode()

    async with aiohttp.ClientSession() as session:
        try:
            headers = {
                'X-API-Key': os.getenv('clyppy_post_key'),
                'Content-Type': 'application/json'
            }
            data = aiohttp.FormData()
            data.add_field('file', file_data)
            data.add_field('filename', os.path.basename(video_file_path))
            async with session.post('https://clyppy.io/api/addclip/',
                                    data=data, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return None
        except Exception as e:
            raise e


class BaseClip(ABC):
    """Base class for all clip types"""

    def __init__(self, slug: str):
        self.service = None
        self.url = None
        self.id = slug
        self.clyppy_id = self._generate_clyppy_id(slug)
        self.clyppy_url = f"https://clyppy.io/{self.clyppy_id}"
        self.logger = logging.getLogger(__name__)

    async def download(self, filename=None, dlp_format='best[ext=mp4]') -> Optional[DownloadResponse]:
        """
        Gets direct media URL and duration from the clip URL without downloading.
        Returns tuple of (direct_url, duration_in_seconds) or None if extraction fails.
        """
        ydl_opts = {
            'format': dlp_format,
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

    def _extract_info(self, ydl_opts: dict) -> DownloadResponse:
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
                # the file is hosted by the service's cdn
                rmurl = info['url']
                self.logger.info(f"Found [best] direct URL: {rmurl}")
                return DownloadResponse(
                    remote_url=rmurl,
                    local_file_path=None,
                    duration=duration
                )
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
                    rmurl = best_format['url']
                    self.logger.info(f"Found direct URL: {rmurl}")
                    return DownloadResponse(
                        remote_url=rmurl,
                        local_file_path=None,
                        duration=duration
                    )
            # the file cannot be retrieved directly and needs to be downloaded by another means, then uploaded to clyppy.io
            raise ValueError("No suitable URL found in video info")

    @staticmethod
    def _generate_clyppy_id(input_str: str, length: int = 8) -> str:
        """
        Generates a fixed-length lowercase ID from any input string.
        Will always return the same ID for the same input.

        Args:
            input_str: Any string input to generate ID from
            length: Desired length of output ID (default 8)

        Returns:
            A fixed-length lowercase alphanumeric string
        """
        # Create hash of input
        hash_object = hashlib.sha256(input_str.encode())
        hash_hex = hash_object.hexdigest()

        # Convert to base36 (lowercase letters + numbers)
        # First convert hex to int, then to base36
        hash_int = int(hash_hex, 16)
        base36 = '0123456789abcdefghijklmnopqrstuvwxyz'
        base36_str = ''

        while hash_int:
            hash_int, remainder = divmod(hash_int, 36)
            base36_str = base36[remainder] + base36_str
        # Take first 'length' characters, pad with 'a' if too short
        result = base36_str[:length]
        if len(result) < length:
            result = result + 'a' * (length - len(result))
        return result


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
