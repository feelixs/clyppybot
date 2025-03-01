from abc import ABC, abstractmethod
from yt_dlp import YoutubeDL
from typing import Tuple, Optional, Union
from dataclasses import dataclass
from moviepy.video.io.VideoFileClip import VideoFileClip
from interactions import Message, SlashContext
from yt_dlp.utils import DownloadError
from bot.upload import UploadFailed
from bot.tools.misc import get_aiohttp_session
from bot.cdn import CdnSpacesClient
import aiohttp
import hashlib
import logging
import asyncio
import os


def tryremove(f):
    try:
        os.remove(f)
    except:
        pass


def is_discord_compatible(filesize: float):
    if filesize is None:
        return False
    return MAX_FILE_SIZE_FOR_DISCORD > filesize > 0


MAX_VIDEO_LEN_SEC = 60 * 5
MAX_FILE_SIZE_FOR_DISCORD = 8 * 1024 * 1024
DL_SERVER_ID = os.getenv("DL_SERVER_ID")
EMBED_TOKEN_COST = 1
EMBED_W_TOKEN_MAX_LEN = 30 * 60  # 30 minutes


class UnknownError(Exception):
    pass


class InvalidClipType(Exception):
    pass


class VideoTooLong(Exception):
    pass


class NoPermsToView(Exception):
    pass


class NoDuration(Exception):
    pass


class ClipFailure(Exception):
    pass


async def is_404(url: str, logger=None) -> Tuple[bool, int]:
    try:
        async with get_aiohttp_session() as session:
            async with session.get(url) as response:
                if logger is not None:
                    logger.info(f"Got response status {response.status} for {url}")
                return not str(response.status).startswith('2'), response.status
    except aiohttp.ClientError:
        # Handle connection errors, invalid URLs etc
        return True, 500  # Consider failed connections as effectively 404


def get_video_details(file_path) -> 'LocalFileInfo':
    try:
        clip = VideoFileClip(file_path)
        try:
            size = os.path.getsize(file_path)
        except OSError:
            size = 0
        return LocalFileInfo(
            width=clip.w,
            height=clip.h,
            filesize=size,
            duration=clip.duration,
            local_file_path=file_path,
            video_name=None,
            can_be_uploaded=is_discord_compatible(size)
        )
        #return {
        #    'width': clip.w,
        #    'height': clip.h,
        #    'url': url,
        #    'filesize': os.path.getsize(file_path),
        #    'duration': clip.duration
        #}
    except Exception as e:
        raise
    finally:
        # Make sure we close the clip to free resources
        if 'clip' in locals():
            clip.close()


def fetch_cookies(opts, logger):
    try:
        profile_dir = None
        for item in os.listdir('/firefox-profiles'):
            if item.endswith('.default-release'):
                profile_dir = item
                break

        if profile_dir:
            profile_path = f"/firefox-profiles/{profile_dir}"
            logger.info(f"Using Firefox profile: {profile_path}")
            cookies_string = ('firefox', profile_path, None, None)
            opts['cookiesfrombrowser'] = cookies_string
            return

        logger.info("No Firefox profile found.")
    except Exception as e:
        logger.error(f"Error fetching cookies: {str(e)}")


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


class BaseClip(ABC):
    """Base class for all clip types"""

    @abstractmethod
    def __init__(self, slug: str, cdn_client: CdnSpacesClient):
        self.cdn_client = cdn_client
        self.id = slug
        self.clyppy_id = self._generate_clyppy_id(f"{self.service}{slug}")
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Generated clyppy ID: {self.clyppy_id} for {self.service}, {slug}")
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
                    self.logger.info("Using default dimensions of 1280x720 for twitch clip")
                    format_info = extract_format_info(fmt=info, h=720, w=1280)
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

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False) -> DownloadResponse:
        resp = await self._fetch_external_url(dlp_format, cookies)
        self.logger.info(f"[download] Got filesize {resp.filesize} for {self.id}")
        if is_discord_compatible(resp.filesize) and can_send_files:
            self.logger.info(f"{self.id} can be uploaded to discord, run dl_download instead...")
            local = await self.dl_download(
                    filename=filename,
                    dlp_format=dlp_format,
                    can_send_files=can_send_files,
                    cookies=cookies
                )
            return DownloadResponse(
                    remote_url=None,
                    local_file_path=local.local_file_path,
                    duration=local.duration,
                    width=local.width,
                    height=local.height,
                    filesize=local.filesize,
                    video_name=local.video_name,
                    can_be_uploaded=True
                )
        else:
            resp.filesize = 0  # it's hosted on external cdn, not clyppy.io, so make this 0 to reduce confusion
            return resp

    async def _fetch_external_url(self, dlp_format='best/bv*+ba', cookies=False) -> DownloadResponse:
        """
        Gets direct media URL and duration from the clip URL without downloading.
        Returns tuple of (direct_url, duration_in_seconds) or None if extraction fails.
        """
        ydl_opts = {
            'format': dlp_format,
            'quiet': True,
            'no_warnings': True,
        }
        if cookies:
            fetch_cookies(ydl_opts, self.logger)

        try:
            return await asyncio.get_event_loop().run_in_executor(
                None,
                self._extract_info,
                ydl_opts
            )
        except Exception as e:
            self.logger.error(f"Failed to get direct URL: {str(e)}")
            raise NoDuration

    async def _fetch_file(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False, useragent=None) -> LocalFileInfo:
        local_file = await self.dl_download(filename, dlp_format, can_send_files, cookies, useragent)
        if local_file is None:
            raise UnknownError
        return local_file

    async def dl_check_size(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, upload_if_large=False, cookies=False, useragent=None) -> Optional[DownloadResponse]:
        """
            Download the clip file, and return the local file info if its within Discord's file size limit,
            otherwise return None
        """
        local = None
        if can_send_files:
            local = await self._fetch_file(filename, dlp_format, can_send_files, cookies, useragent)
            self.logger.info(f"[dl_check_size] Got filesize {round(local.filesize / 1024 / 1024, 2)}MB for {self.id}")
            if is_discord_compatible(local.filesize):
                return DownloadResponse(
                    remote_url=None,
                    local_file_path=local.local_file_path,
                    duration=local.duration,
                    width=local.width,
                    height=local.height,
                    filesize=local.filesize,
                    video_name=local.video_name,
                    can_be_uploaded=True
                )

        if upload_if_large:
            if local is None:
                local = await self._fetch_file(filename, dlp_format, can_send_files, cookies, useragent)
            self.logger.info(f"{self.id} is too large to upload to discord, uploading to clyppy.io instead...")
            return await self.upload_to_clyppyio(local)

        return None

    async def dl_download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False, useragent=None) -> LocalFileInfo:
        if os.path.isfile(filename):
            self.logger.info("file already exists! returning...")
            return get_video_details(filename)

        ydl_opts = {
            'format': dlp_format,
            'outtmpl': filename,
            'quiet': True,
            'no_warnings': True,
        }
        if useragent:
            ydl_opts['user_agent'] = useragent

        if cookies:
            fetch_cookies(ydl_opts, self.logger)

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
                if is_discord_compatible(d.filesize) and can_send_files:
                    self.logger.info(f"{self.id} can be uploaded to discord...")
                    d.can_be_uploaded = True

                return d

            self.logger.info(f"Could not find file")
            raise UnknownError
        except Exception as e:
            self.logger.error(f"yt-dlp download error: {str(e)}")
            raise

    async def overwrite_mp4(self, new_url: str):
        url = 'https://clyppy.io/api/overwrite/'
        headers = {
            'X-API-Key': os.getenv('clyppy_post_key'),
            'Content-Type': 'application/json'
        }
        j = {'id': self.clyppy_id, 'url': new_url}
        async with get_aiohttp_session() as session:
            async with session.post(url, json=j, headers=headers) as response:
                if response.status in [201, 202]:
                    return await response.json()
                else:
                    error_data = await response.json()
                    raise Exception(f"Failed to overwrite clip data: {error_data.get('error', 'Unknown error')}")

    async def upload_to_clyppyio(self, local_file_info: LocalFileInfo) -> DownloadResponse:
        try:
            success, remote_url = await self.cdn_client.cdn_upload_video(
                file_path=local_file_info.local_file_path
            )
        except Exception as e:
            self.logger.error(f"Failed to upload video: {str(e)}")
            raise UploadFailed
        if success:
            self.logger.info(f"Uploaded video: {remote_url}")
            return DownloadResponse(
                remote_url=remote_url,
                local_file_path=local_file_info.local_file_path,
                duration=local_file_info.duration,
                filesize=local_file_info.filesize,
                height=local_file_info.height,
                width=local_file_info.width,
                video_name=local_file_info.video_name,
                can_be_uploaded=None
            )
        else:
            self.logger.error(f"Failed to upload video: {remote_url}")
            raise UploadFailed

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
    def __init__(self, cdn_client: CdnSpacesClient):
        self.logger = logging.getLogger(__name__)
        self.platform_name = None
        self.is_nsfw = False
        self.dl_timeout_secs = 30
        self.cdn_client = cdn_client

    @abstractmethod
    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'BaseClip':
        ...

    @abstractmethod
    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        ...

    def is_clip_link(self, url: str) -> bool:
        """
            Checks if a URL is a valid link format.
        """
        return bool(self.parse_clip_url(url))

    @staticmethod
    async def subtract_tokens(user, amt):
        url = 'https://clyppy.io/api/tokens/subtract/'
        headers = {
            'X-API-Key': os.getenv('clyppy_post_key'),
            'Content-Type': 'application/json'
        }
        j = {'userid': user.id, 'username': user.username, 'amount': amt}
        async with get_aiohttp_session() as session:
            async with session.post(url, json=j, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_data = await response.json()
                    raise Exception(f"Failed to subtract user's VIP tokens: {error_data.get('error', 'Unknown error')}")

    async def get_len(self, url: str, cookies=False, download=False) -> float:
        """
            Uses yt-dlp to check video length of the provided url
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'verbose': False,
            'extract_flat': not download,  # only extract metadata, (it won't download if this is true)
        }
        if cookies:
            fetch_cookies(ydl_opts, self.logger)

        if download:
            # Add max filesize option when downloading
            ydl_opts['max_filesize'] = 1610612736  # 1.5GB in bytes (1.5 * 1024 * 1024 * 1024) should handle most 45 min videos

        try:
            # Run yt-dlp in an executor to avoid blocking
            def get_duration():
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=download)
                    if download:
                        # Handle different metadata structures
                        if 'filepath' in info:
                            return get_video_details(info['filepath'])
                        elif '_filename' in info:
                            return get_video_details(info['_filename'])
                        elif 'requested_downloads' in info and len(info['requested_downloads']) > 0:
                            # Some platforms use this structure
                            download_info = info['requested_downloads'][0]
                            if 'filepath' in download_info:
                                return get_video_details(download_info['filepath'])
                            elif '_filename' in download_info:
                                return get_video_details(download_info['_filename'])

                        # If we can't find the file path, log the info structure
                        self.logger.error(f"Could not find filepath in info: {info.keys()}")
                        raise NoDuration
                    else:
                        return info.get('duration', 0)

            duration = await asyncio.get_event_loop().run_in_executor(
                None, get_duration
            )
            return duration

        except DownloadError as e:
            self.logger.error(f"Error downloading video for {url}: {str(e)}")
            if 'You don\'t have permission' in str(e):
                raise NoPermsToView
            raise VideoTooLong
        except Exception as e:
            self.logger.error(f"Error checking video length for {url}: {str(e)}")
            if 'MoviePy error: failed to read the first frame of video file' in str(e):
                raise VideoTooLong
            raise NoDuration

    async def is_shortform(self, url: str, basemsg: Union[Message, SlashContext], cookies=False) -> bool:
        try:
            d = await self.get_len(url, cookies)
        except NoDuration:
            d = None

        if d is None or d == 0:
            # yt-dlp unable to fetch duration directly, need to download the file to verify manually
            self.logger.info(f"yt-dlp unable to fetch duration for {url}, downloading to verify...")
            file = await self.get_len(url, cookies, download=True)
            self.logger.info(f'Downloaded {file.local_file_path} from {url} to verify...')
            d = file.duration

        if d <= MAX_VIDEO_LEN_SEC:  # no tokens need to be used
            return True
        elif d <= EMBED_W_TOKEN_MAX_LEN:  # use the tokens (the video will embed if they're deducted successfully)
            if isinstance(basemsg, Message):
                user = basemsg.author
            else:
                user = basemsg.user

            # if we're in dl server, automatically return true without needing any tokens
            if self.is_dl_server(basemsg.guild):
                return True

            sub = await self.subtract_tokens(user, EMBED_TOKEN_COST)
            if sub['success']:
                if sub['user_success']:  # the user had enough tokens to subtract successfully
                    return True

        return False

    @staticmethod
    def is_dl_server(guild):
        if guild is None:
            return False
        elif str(guild.id) == str(DL_SERVER_ID):
            return True
        return False
