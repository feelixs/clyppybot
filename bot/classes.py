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
from moviepy.video.io.VideoFileClip import VideoFileClip


async def is_404(url: str) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return response.status == 404
    except aiohttp.ClientError:
        # Handle connection errors, invalid URLs etc
        return True  # Consider failed connections as effectively 404


def get_video_details(file_path, url):
    try:
        clip = VideoFileClip(file_path)
        return {
            'width': clip.w,
            'height': clip.h,
            'url': url,
            'filesize': os.path.getsize(file_path),
            'duration': clip.duration
        }
    finally:
        # Make sure we close the clip to free resources
        if 'clip' in locals():
            clip.close()


@dataclass
class DownloadResponse:
    remote_url: Optional[str]
    local_file_path: Optional[str]
    duration: float
    width: int
    height: int
    filesize: float


async def upload_video(video_file_path):
    # Read and encode the file
    with open(video_file_path, 'rb') as f:
        file_data = base64.b64encode(f.read()).decode()

    data = {
        'file': file_data,
        'filename': os.path.basename(video_file_path)
    }

    async with aiohttp.ClientSession() as session:
        try:
            headers = {
                'X-API-Key': os.getenv('clyppy_post_key'),
                'Content-Type': 'application/json'
            }
            async with session.post(
                    'https://clyppy.io/api/addclip/',
                    json=data,
                    headers=headers
            ) as response:
                return await response.json()
        except Exception as e:
            raise e


class BaseClip(ABC):
    """Base class for all clip types"""

    @abstractmethod
    def __init__(self, slug: str):
        self.id = slug
        self.clyppy_id = self._generate_clyppy_id(f"{self.service}{slug}")
        self.logger = logging.getLogger(__name__)

    @property
    @abstractmethod
    def service(self) -> str:
        """Service name must be implemented by child classes"""
        pass

    @property
    @abstractmethod
    def url(self) -> str:
        pass

    @property
    def clyppy_url(self) -> str:
        """Generate the clyppy URL using the service and ID"""
        return f"https://clyppy.io/{self.clyppy_id}"

    async def download(self, filename=None, dlp_format='best[ext=mp4]') -> Optional[DownloadResponse]:
        """
        Gets direct media URL and duration from the clip URL without downloading.
        Returns tuple of (direct_url, duration_in_seconds) or None if extraction fails.
        """
        ydl_opts = {
            'format': dlp_format,
            'quiet': True,
            'no_warnings': True,
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
        Helper method to extract URL, duration, file size and dimension information using yt-dlp.
        Runs in thread pool to avoid blocking the event loop.
        """
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(self.url, download=False)
            if not info:
                raise ValueError("Could not extract video information")

            # Get duration
            duration = info.get('duration', 0)

            def extract_format_info(fmt):
                """Helper to extract format details"""
                return {
                    'url': fmt.get('url'),
                    'filesize': fmt.get('filesize') or fmt.get('filesize_approx', 0),
                    'width': fmt.get('width'),
                    'height': fmt.get('height'),
                }

            # Get direct URL and format info
            if 'url' in info:
                # Direct URL available in info
                format_info = extract_format_info(info)
                if format_info['width'] is None:
                    self.logger.info("width was 0 lets check manually")
                    # we need to download the file now, and determine the width
                    o = ydl_opts.copy()
                    fn = f'temp{self.id}.mp4'
                    o['outtmpl'] = fn
                    with YoutubeDL(o) as tmpdl:
                        tmpdl.download([self.url])
                    self.logger.info(os.path.isfile(fn))
                    format_info = get_video_details(fn, info['url'])
                    os.remove(fn)

                self.logger.info(f"Found [best] direct URL: {format_info['url']}")
                return DownloadResponse(
                    remote_url=format_info['url'],
                    local_file_path=None,
                    duration=duration,
                    filesize=format_info['filesize'],
                    width=format_info['width'],
                    height=format_info['height']
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
                    format_info = extract_format_info(best_format)
                    self.logger.info(f"Found direct URL: {format_info['url']}")
                    return DownloadResponse(
                        remote_url=format_info['url'],
                        local_file_path=None,
                        duration=duration,
                        filesize=format_info['filesize'],
                        width=format_info['width'],
                        height=format_info['height']
                    )

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

    async def is_shortform(self, url: str, max_len=120) -> bool:
        d = await self.get_len(url)
        if d is None:
            return False
        return d <= max_len
