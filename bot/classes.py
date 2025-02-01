from abc import ABC, abstractmethod
import logging
import asyncio
import os
from yt_dlp import YoutubeDL
from typing import Tuple, Optional, Dict
from dataclasses import dataclass
import base64
import aiohttp
from urllib.parse import urlparse, parse_qs
import hashlib
from moviepy.video.io.VideoFileClip import VideoFileClip
import json
from datetime import datetime, timezone


MAX_VIDEO_LEN_SEC = 180
MAX_FILE_SIZE_FOR_DISCORD = 8 * 1024 * 1024


class InvalidClipType(Exception):
    pass


class VideoTooLong(Exception):
    pass


# todo: pass cookies into twitter to see nsfw content

class NoDuration(Exception):
    pass


class KickClipFailure(Exception):
    pass



async def is_404(url: str, logger=None) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if logger is not None:
                    logger.info(f"Got response status {response.status} for {url}")
                return not str(response.status).startswith('2')
    except aiohttp.ClientError:
        # Handle connection errors, invalid URLs etc
        return True  # Consider failed connections as effectively 404


def get_video_details(file_path) -> 'LocalFileInfo':
    try:
        clip = VideoFileClip(file_path)
        return LocalFileInfo(
            width=clip.w,
            height=clip.h,
            filesize=os.path.getsize(file_path),
            duration=clip.duration,
            local_file_path=file_path,
            video_name=None,
            can_be_uploaded=None
        )
        #return {
        #    'width': clip.w,
        #    'height': clip.h,
        #    'url': url,
        #    'filesize': os.path.getsize(file_path),
        #    'duration': clip.duration
        #}
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
    video_name: Optional[str]
    can_be_uploaded: Optional[bool]


@dataclass
class LocalFileInfo:
    local_file_path: Optional[str]
    duration: float
    width: int
    height: int
    filesize: float
    video_name: Optional[str]
    can_be_uploaded: Optional[bool]


async def upload_video(video_file_path) -> Dict:
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
        self.title = None

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

            def extract_format_info(fmt, h=None, w=None):
                """Helper to extract format details"""
                a = {
                    'url': fmt.get('url'),
                    'width': fmt.get('width', 0),
                    'height': fmt.get('height', 0),
                }
                if h is not None:
                    a['height'] = h
                if w is not None:
                    a['width'] = w
                return a

            # Get direct URL and format info
            if 'url' in info:
                # Direct URL available in info
                if "production.assets.clips.twitchcdn.net" in info['url']:
                    # if its a twitch or kick clip, we can use a default height/width (kick class already handles this)
                    self.logger.info("Using default dimensions of 1920x1080 for twitch clip")
                    format_info = extract_format_info(fmt=info, h=1080, w=1920)
                else:
                    format_info = extract_format_info(info)
                if not format_info['width']:
                    self.logger.info("Width was 0, checking manually")
                    # Download file to determine width
                    o = ydl_opts.copy()
                    fn = f'temp{self.id}.mp4'
                    o['outtmpl'] = fn
                    with YoutubeDL(o) as tmpdl:
                        tmpdl.download([self.url])
                    self.logger.info(os.path.isfile(fn))
                    format_info = get_video_details(fn)
                    format_info = {
                        'url': info['url'],
                        'duration': format_info.duration,
                        'width': format_info.width,
                        'height': format_info.height
                    }
                    os.remove(fn)

                if info.get('title') is not None:
                    title = info['title']
                    self.title = title
                else:
                    title = None

                self.logger.info(f"Found [best] direct URL")
                return DownloadResponse(
                    remote_url=format_info['url'],
                    local_file_path=None,
                    duration=duration,
                    filesize=info.get('filesize', 0),
                    width=format_info['width'],
                    height=format_info['height'],
                    video_name=title,
                    can_be_uploaded=None
                )
            elif 'formats' in info and info['formats']:
                # Get best MP4 format
                mp4_formats = [f for f in info['formats'] if f.get('ext') == 'mp4']
                if mp4_formats:
                    # Sort by quality with safe default values
                    def get_sort_key(fmt):
                        # Use 0 as default for both filesize and tbr
                        filesize = fmt.get('filesize', 0) or 0
                        tbr = fmt.get('tbr', 0) or 0
                        return filesize or tbr  # Return filesize if present, otherwise tbr

                    best_format = sorted(
                        mp4_formats,
                        key=get_sort_key,
                        reverse=True
                    )[0]
                    format_info = extract_format_info(best_format)
                    self.logger.info(f"Found direct URL: {format_info['url']}")
                    if info.get('title') is not None:
                        title = info['title']
                        self.title = title
                    else:
                        title = None
                    if not format_info['width']:
                        self.logger.info("in 'get best mp4 format' the width was 0, so we're gonna use the default 1280x720")
                        format_info['height'] = 720
                        format_info['width'] = 1280
                    return DownloadResponse(
                        remote_url=format_info['url'],
                        local_file_path=None,
                        duration=duration,
                        filesize=best_format.get('filesize', 0),
                        width=format_info['width'],
                        height=format_info['height'],
                        video_name=title,
                        can_be_uploaded=None
                    )

            raise ValueError("No suitable URL found in video info")

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False) -> Optional[DownloadResponse]:
        resp = await self._fetch_external_url(dlp_format)
        if MAX_FILE_SIZE_FOR_DISCORD > resp.filesize > 0 and can_send_files:
            self.logger.info(f"{self.id} can be uploaded to discord...")
            resp.can_be_uploaded = True
            resp.filesize = 0  # if it's uploaded to discord, we don't need to worry about monitoring its space on clyppy.io
            return resp
        else:
            resp.filesize = 0  # it's hosted on external cdn, not clyppy.io, so make this 0 to reduce confusion
            return resp

    async def _fetch_external_url(self, dlp_format='best/bv*+ba') -> Optional[DownloadResponse]:
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
            return await asyncio.get_event_loop().run_in_executor(
                None,
                self._extract_info,
                ydl_opts
            )
        except Exception as e:
            self.logger.error(f"Failed to get direct URL: {str(e)}")
            return None

    async def dl_download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False) -> Optional[LocalFileInfo]:
        if os.path.isfile(filename):
            self.logger.info("file already exists! returning...")
            return get_video_details(filename)

        ydl_opts = {
            'format': dlp_format,
            'outtmpl': filename,
            'quiet': True,
            'no_warnings': True,
        }

        # Download using yt-dlp
        try:
            with YoutubeDL(ydl_opts) as ydl:
                # Run download in a thread pool to avoid blocking
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: ydl.download([self.url])
                )

            if os.path.exists(filename):
                extracted = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._extract_info,
                    ydl_opts
                )

                d = get_video_details(filename)
                d.video_name = extracted.video_name
                if MAX_FILE_SIZE_FOR_DISCORD > d.filesize > 0 and can_send_files:
                    self.logger.info(f"{self.id} can be uploaded to discord...")
                    d.can_be_uploaded = True
                    d.filesize = 0

                return d

            self.logger.info(f"Could not find file")
            return None
        except Exception as e:
            self.logger.error(f"yt-dlp download error: {str(e)}")
            return None

    async def overwrite_mp4(self, new_url: str):
        url = 'https://clyppy.io/api/overwrite/'
        headers = {
            'X-API-Key': os.getenv('clyppy_post_key'),
            'Content-Type': 'application/json'
        }
        j = {'id': self.clyppy_id, 'url': new_url}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=j, headers=headers) as response:
                if response.status == 201:
                    return await response.json()
                else:
                    error_data = await response.json()
                    raise Exception(f"Failed to overwrite clip data: {error_data.get('error', 'Unknown error')}")

    async def upload_to_clyppyio(self, local_file_info: LocalFileInfo) -> Optional[DownloadResponse]:
        try:
            response = await upload_video(local_file_info.local_file_path)
        except Exception as e:
            self.logger.error(f"Failed to upload video: {str(e)}")
            return None
        if response['success']:
            self.logger.info(f"Uploaded video: {response['file_path']}")
            return DownloadResponse(
                remote_url=response['file_path'],
                local_file_path=local_file_info.local_file_path,
                duration=local_file_info.duration,
                filesize=local_file_info.filesize,
                height=local_file_info.height,
                width=local_file_info.width,
                video_name=local_file_info.video_name,
                can_be_uploaded=None
            )
        else:
            self.logger.error(f"Failed to upload video: {response}")
            return None

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
            raise NoDuration

    async def is_shortform(self, url: str, max_len=MAX_VIDEO_LEN_SEC) -> bool:
        d = await self.get_len(url)
        if d is None:
            return False
        return d <= max_len
