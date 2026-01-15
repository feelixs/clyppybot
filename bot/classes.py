from abc import ABC, abstractmethod

from yt_dlp import YoutubeDL
from typing import Optional, Union
from pathlib import Path
from PIL import Image
from time import time
from datetime import datetime
from moviepy.video.io.VideoFileClip import VideoFileClip
from interactions import Message, SlashContext, TYPE_THREAD_CHANNEL, Embed, Permissions, Button, ButtonStyle
from interactions.api.events import MessageCreate

from bot.io.io import author_has_enough_tokens_for_ai_extend
from bot.tools.embedder import AutoEmbedder
from bot.io.cdn import CdnSpacesClient
from bot.io import get_aiohttp_session, get_token_cost, push_interaction_error, author_has_enough_tokens, author_has_premium, fetch_video_status
from bot.types import LocalFileInfo, DownloadResponse, GuildType, COLOR_GREEN, COLOR_RED
from bot.env import (EMBED_TXT_COMMAND, create_nexus_comps, APPUSE_LOG_WEBHOOK, EMBED_TOKEN_COST, MAX_VIDEO_LEN_SEC,
                     EMBED_TOTAL_MAX_LENGTH, EMBED_W_TOKEN_MAX_LEN, LOGGER_WEBHOOK, SUPPORT_SERVER_URL, VERSION,
                     CLYPPY_VOTE_URL, DL_SERVER_ID, YT_DLP_MAX_FILESIZE, MAX_FILE_SIZE_FOR_DISCORD, YT_DLP_USER_AGENT,
                     MAX_VIDEO_LEN_FOR_EXTEND, MIN_VIDEO_LEN_FOR_EXTEND, BUY_TOKENS_URL, AI_EXTEND_TOKENS_COST,
                     GITHUB_URL)
from bot.errors import (NoDuration, UnknownError, UploadFailed, NoPermsToView, VideoTooLong, VideoLongerThanMaxLength,
                        IPBlockedError, VideoUnavailable, InvalidFileType, UnsupportedError, RemoteTimeoutError,
                        YtDlpForbiddenError, UrlUnparsable, VideoSaidUnavailable, DefinitelyNoDuration,
                        handle_yt_dlp_err, VideoTooShortForExtend, VideoTooLongForExtend, VideoExtensionFailed,
                        VideoContainsNSFWContent, ExceptionHandled)

import hashlib
import aiohttp
import logging
import asyncio
import random
import os

def tryremove(f):
    try:
        os.remove(f)
    except:
        pass


def get_random_face():
    faces = ['(⌯˃̶᷄ ﹏ ˂̶᷄⌯)', '`ヽ(゜～゜o)ノ`', '( ͡ಠ ͜ʖ ͡ಠ)', '(╯°□°)╯︵ ┻━┻', '乁( ⁰͡ Ĺ̯ ⁰͡ ) ㄏ', r'¯\_(ツ)_/¯']
    return f'{random.choice(faces)}'


def is_discord_compatible(filesize: float):
    if filesize is None:
        return False
    return MAX_FILE_SIZE_FOR_DISCORD > filesize > 0


def infer_video_dimensions(width: Optional[int], height: Optional[int]) -> tuple[int, int]:
    """
    Intelligently infers correct video dimensions based on common aspect ratios.
    Fixes cases where only partial dimensions are available or dimensions don't match valid aspect ratios.

    Logic:
    - If both dimensions provided with valid aspect ratio, return as-is
    - If both provided but invalid ratio (like 1280x1080), infer correct dimensions
    - If only one dimension provided, check if it matches common mobile/desktop values
    - Mobile (9:16): heights 1920/1280 or widths 1080/720
    - Desktop (16:9): fallback for all other cases
    - Default: 1280x720 if neither dimension provided

    Args:
        width: Video width in pixels (can be None)
        height: Video height in pixels (can be None)

    Returns:
        Tuple of (width, height) with proper aspect ratio
    """
    # Common mobile heights/widths for 9:16 portrait videos
    MOBILE_HEIGHTS = {1920, 1280}
    MOBILE_WIDTHS = {1080, 720}

    # If both are provided, check if they form a valid aspect ratio
    if width is not None and height is not None:
        # Calculate aspect ratio
        aspect_ratio = width / height if height > 0 else 0

        # Common valid aspect ratios (with some tolerance)
        # 16:9 = 1.777, 9:16 = 0.5625, 4:3 = 1.333, 1:1 = 1.0, 4:5 = 0.8
        valid_ratios = [
            (16/9, 0.05),   # 16:9 landscape (±5% tolerance)
            (9/16, 0.05),   # 9:16 portrait
            (4/3, 0.05),    # 4:3 old standard
            (1.0, 0.05),    # 1:1 square
            (4/5, 0.05),    # 4:5 Instagram portrait
        ]

        # Check if aspect ratio is valid
        for ratio, tolerance in valid_ratios:
            if abs(aspect_ratio - ratio) <= tolerance:
                # Valid aspect ratio, return as-is
                return (width, height)

        # Invalid aspect ratio detected (e.g., 1280x1080) - need to infer correct dimensions
        # Use the larger dimension and apply proper aspect ratio
        if height > width:
            # Likely portrait, check if height matches mobile
            if height in MOBILE_HEIGHTS:
                corrected_width = int(height * 9 / 16)
                return (corrected_width, height)
            else:
                # Unusual portrait, use 9:16 anyway
                corrected_width = int(height * 9 / 16)
                return (corrected_width, height)
        else:
            # Likely landscape - use 16:9
            corrected_height = int(width * 9 / 16)
            return (width, corrected_height)

    # If only height is provided
    if height is not None and width is None:
        if height in MOBILE_HEIGHTS:
            # Mobile aspect ratio 9:16
            inferred_width = int(height * 9 / 16)
            return (inferred_width, height)
        else:
            # Desktop aspect ratio 16:9
            inferred_width = int(height * 16 / 9)
            return (inferred_width, height)

    # If only width is provided
    if width is not None and height is None:
        if width in MOBILE_WIDTHS:
            # Mobile aspect ratio 9:16
            inferred_height = int(width * 16 / 9)
            return (width, inferred_height)
        else:
            # Desktop aspect ratio 16:9
            inferred_height = int(width * 9 / 16)
            return (width, inferred_height)

    # Neither provided, return default desktop dimensions
    return (1280, 720)


async def send_webhook(logger, content: Optional[str] = None, title: Optional[str] = None, load: Optional[str] = None, url: Optional[str]=None, color=None, in_test=False, embed=True):
    if not in_test and os.getenv("TEST"):
        return

    if url is None:
        url = LOGGER_WEBHOOK

    # Create a rich embed
    if color is None:
        color = 5814783  # Blue color

    e = []
    if title is not None and load is not None and embed:
        e = [{
                "title": title,
                "description": load,
                "color": color,
            }]
    elif not embed:
        if content is None:
            content = ""
        content += f"\n\n**{title}**\n{load}"

    payload = {
        "content": content,
        "embeds": e
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload) as response:
                if response.status == 204:
                    logger.info(f"Successfully sent logger webhook: {load}")
                else:
                    logger.info(f"Failed to send logger webhook. Status: {response.status}")
                return response.status
        except Exception as e:
            logger.info(f"Error sending log webhook: {str(e)}")
            return None


def get_video_details(file_path) -> 'LocalFileInfo':
    clip = None
    try:
        # Try initializing without audio processing first
        clip = VideoFileClip(file_path, audio=False)
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
            can_be_discord_uploaded=is_discord_compatible(size)
        )
    except Exception as e:
        # Log the specific error before re-raising
        logging.getLogger(__name__).error(f"Error getting video details for {file_path}: {e}")
        raise
    finally:
        # Make sure we close the clip to free resources if it was created
        if clip is not None:
            clip.close()


def fetch_cookies(opts, logger):
    try:
        # Try cookie file first (downloaded from server)
        cookie_file = os.getenv("COOKIE_FILE")
        if cookie_file and os.path.exists(cookie_file):
            logger.info(f"Using cookie file: {cookie_file}")
            opts['cookiefile'] = cookie_file
            return

        # Fallback to Firefox profile (original behavior)
        cookie_dir = os.getenv("COOKIE_DIR")
        if cookie_dir is None:
            logger.info("No COOKIE_FILE or COOKIE_DIR set, skipping cookies")
            return

        firefox_dir = Path(cookie_dir).expanduser()
        if not firefox_dir.exists():
            logger.warning(f"[COOKIES] firefox directory does not exist: {cookie_dir}")
            return

        profile_dirs = list(firefox_dir.glob("*.default-release"))
        if profile_dirs:
            profile_path = str(profile_dirs[0])
            logger.info(f"Using Firefox profile: {profile_path}")
            cookies_string = ('firefox', profile_path, None, None)
            opts['cookiesfrombrowser'] = cookies_string
            return

        logger.info("No Firefox profile found.")
    except Exception as e:
        logger.error(f"Error fetching cookies: {str(e)}")


class BaseClip(ABC):
    """Base class for all clip types"""

    @abstractmethod
    def __init__(self, slug: str, cdn_client: CdnSpacesClient, tokens_used: int, duration: int):
        self.cdn_client = cdn_client
        self.id = slug
        self._clyppy_id_input = f"{self.service}{slug}"
        self.is_discord_attachment = False
        self.duration = duration
        self.tokens_used = tokens_used
        self.clyppy_id = None
        self.logger = logging.getLogger(__name__)
        self.title = None

    async def compute_clyppy_id(self):
        # Generate new format (base62, 10-char) ID
        new_id = self._generate_clyppy_id(self._clyppy_id_input, low_collision=True)

        # Check if new format exists
        status = await fetch_video_status(new_id)
        if status['exists']:
            self.clyppy_id = new_id
            self.logger.info(f"Found existing video with new ID format: {self.clyppy_id}")
            return

        # Fallback: check old format (base36, 8-char) for backward compatibility
        old_id = self._generate_clyppy_id(self._clyppy_id_input, low_collision=False)
        self.logger.info(f"Checking existance of old id: {old_id}")
        status = await fetch_video_status(old_id)
        if status['exists']:
            self.clyppy_id = old_id
            self.logger.info(f"Found existing video with old ID format: {self.clyppy_id}")
            return

        # No existing video found, use new format for new videos
        self.clyppy_id = new_id
        self.logger.info(f"Generated new clyppy ID (base62): {self.clyppy_id} for {self._clyppy_id_input}")

    @property
    @abstractmethod
    def service(self) -> str:
        """Service name must be implemented by child classes"""
        pass

    @property
    @abstractmethod
    def url(self) -> str:
        """Url yt-dlp will use to extract video information"""
        pass

    @property
    def share_url(self) -> Optional[str]:
        """If different from url property"""
        return None

    @property
    def clyppy_url(self) -> str:
        """Generate the clyppy URL using the service and ID"""
        return f"https://clyppy.io/{self.clyppy_id}"

    async def get_thumbnail(self):
        return None

    def _extract_info(self, ydl_opts: dict) -> DownloadResponse:
        """
        Helper method to extract URL, duration, file size and dimension information using yt-dlp.
        Runs in thread pool to avoid blocking the event loop.
        """
        # Add options to prevent ffmpeg extraction issues
        ydl_opts.update({
            'skip_download': True,  # Explicit skip download
            'postprocessors': [],   # No post-processing
            'extract_flat': True,   # Only extract metadata
            'youtube_include_dash_manifest': False,  # Skip DASH manifest parsing
            'ignoreerrors': True    # Continue on errors
        })
        
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(self.url, download=False)
                if not info:
                    raise ValueError("Could not extract video information")

                # Get duration with fallback
                duration = info.get('duration', 0)
                if duration <= 0:
                    self.logger.warning(f"Got invalid duration {duration} for {self.url}")

                def extract_format_info(fmt, h=None, w=None):
                    """Helper to extract format details with intelligent dimension inference"""
                    # Get width and height from format, or use provided defaults
                    raw_width = fmt.get('width', w)
                    raw_height = fmt.get('height', h)

                    # Use inference to ensure proper aspect ratio
                    inferred_width, inferred_height = infer_video_dimensions(raw_width, raw_height)

                    # Log if dimensions were inferred vs extracted
                    if raw_width != inferred_width or raw_height != inferred_height:
                        self.logger.info(
                            f"Inferred dimensions: {raw_width}x{raw_height} -> {inferred_width}x{inferred_height}"
                        )

                    return {
                        'url': fmt.get('url', ''),
                        'width': inferred_width,
                        'height': inferred_height,
                    }

                # Try to get direct URL first
                if 'url' in info and info['url']:
                    # Handle special cases for known platforms
                    if "production.assets.clips.twitchcdn.net" in info['url']:
                        format_info = extract_format_info(info, h=720, w=1280)
                        self.logger.info(f"Using default dimensions for Twitch clip {format_info['width']}x{format_info['height']}")
                    else:
                        format_info = extract_format_info(info)

                    return DownloadResponse(
                        remote_url=format_info['url'],
                        local_file_path=None,
                        duration=duration,
                        filesize=info.get('filesize', 0),
                        width=format_info['width'],
                        height=format_info['height'],
                        video_name=info.get('title'),
                        can_be_discord_uploaded=None,
                        clyppy_object_is_stored_as_redirect=False
                    )

                # Fall back to formats list if direct URL not available
                if 'formats' in info and info['formats']:
                    # Get all video formats (not just mp4)
                    video_formats = [f for f in info['formats'] if f.get('vcodec') != 'none' and f.get('url')]
                    
                    if video_formats:
                        # Sort by quality - prefer higher resolution and filesize
                        best_format = max(video_formats,
                                          key=lambda f: (
                                              f.get('width', 0),
                                              f.get('height', 0),
                                              f.get('filesize', 0)
                                          ))
                        
                        format_info = extract_format_info(best_format)
                        self.logger.info(f"Selected format: {best_format.get('format_id')}")

                        return DownloadResponse(
                            remote_url=format_info['url'],
                            local_file_path=None,
                            duration=duration,
                            filesize=best_format.get('filesize', 0),
                            width=format_info['width'],
                            height=format_info['height'],
                            video_name=info.get('title'),
                            can_be_discord_uploaded=None,
                            clyppy_object_is_stored_as_redirect=False
                        )

                # If we get here, no suitable format was found
                self.logger.error(f"No suitable format found in info: {info.keys()}")
                raise ValueError("No playable formats found")

            except Exception as e:
                self.logger.error(f"Error extracting info for {self.url}: {str(e)}")
                raise

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False, extra_opts=None) -> DownloadResponse:
        resp = await self._fetch_external_url(dlp_format, cookies, extra_opts)
        self.logger.info(f"[download] Got filesize {resp.filesize} for {self.id}")
        if is_discord_compatible(resp.filesize) and can_send_files:
            self.logger.info(f"{self.id} can be uploaded to discord, run dl_download instead...")
            local = await self.dl_download(
                    filename=filename,
                    dlp_format=dlp_format,
                    can_send_files=can_send_files,
                    cookies=cookies,
                    extra_opts=extra_opts
                )
            return DownloadResponse(
                    remote_url=None,
                    local_file_path=local.local_file_path,
                    duration=local.duration,
                    width=local.width,
                    height=local.height,
                    filesize=local.filesize,
                    video_name=local.video_name,
                    can_be_discord_uploaded=True,
                    clyppy_object_is_stored_as_redirect=False
                )
        else:
            resp.filesize = 0  # it's hosted on external cdn, not clyppy.io, so make this 0 to reduce confusion
            return resp

    async def _fetch_external_url(self, dlp_format='best/bv*+ba', cookies=False, extra_opts=None) -> DownloadResponse:
        """
        Gets direct media URL and duration from the clip URL without downloading.
        Returns tuple of (direct_url, duration_in_seconds) or None if extraction fails.
        """
        ydl_opts = {
            'format': dlp_format,
            'quiet': True,
            'no_warnings': True,
            'user_agent': YT_DLP_USER_AGENT
        }

        # Merge extra options (like custom headers for Instagram)
        if extra_opts:
            ydl_opts.update(extra_opts)

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

    async def _fetch_file(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False, extra_opts=None) -> LocalFileInfo:
        local_file = await self.dl_download(filename, dlp_format, can_send_files, cookies, extra_opts)
        if local_file is None: raise UnknownError
        return local_file

    async def dl_check_size(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, upload_if_large=False, cookies=False, extra_opts=None) -> Optional[DownloadResponse]:
        """
            Download the clip file, and return the local file info if its within Discord's file size limit,
            otherwise return None
        """
        local = None
        if can_send_files:
            local = await self._fetch_file(filename, dlp_format, can_send_files, cookies, extra_opts)
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
                    can_be_discord_uploaded=True,
                    clyppy_object_is_stored_as_redirect=False
                )

        if upload_if_large:
            if local is None: local = await self._fetch_file(filename, dlp_format, can_send_files, cookies, extra_opts)
            self.logger.info(f"{self.id} is too large to upload to discord, uploading to clyppy.io instead...")
            return await self.upload_to_clyppyio(local)

        return None

    async def dl_download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False, extra_opts=None) -> Optional[LocalFileInfo]:
        if os.path.isfile(filename):
            self.logger.info("file already exists! returning...")
            return get_video_details(filename)

        ydl_opts = {
            'format': dlp_format,
            'outtmpl': filename,
            'quiet': True,
            'no_warnings': True,
            'user_agent': YT_DLP_USER_AGENT,
            'postprocessor_args': {
                'ffmpeg': ['-fflags', '+shortest', '-max_interleave_delta', '1G']
            }
        }

        # Merge extra options (like custom headers for Instagram)
        if extra_opts:
            ydl_opts.update(extra_opts)

        if cookies: fetch_cookies(ydl_opts, self.logger)
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
                    d.can_be_discord_uploaded = True

                return d

            self.logger.info(f"dl_download error: Could not find file")
            raise FileNotFoundError
        except Exception as e:
            self.logger.error(f"yt-dlp download error: {str(e)}")
            handle_yt_dlp_err(str(e), filename)

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
                can_be_discord_uploaded=None,
                clyppy_object_is_stored_as_redirect=False
            )
        else:
            self.logger.error(f"Failed to upload video: {remote_url}")
            raise UploadFailed

    async def download_first_frame_webp(self, video_url: str, output_path: str) -> str:
        """
        Downloads only the first frame from a remote video URL and saves it as webp.
        Uses ffmpeg to efficiently extract the frame without downloading the full video.

        Args:
            video_url: Remote URL to the video (must be a direct video URL, not a page URL)
            output_path: Path where the webp file will be saved

        Returns:
            Path to the generated webp file

        Raises:
            Exception: If ffmpeg fails to extract the frame
        """
        import subprocess

        cmd = [
            'ffmpeg',
            '-i', video_url,
            '-vframes', '1',
            '-c:v', 'libwebp',
            '-quality', '85',
            '-y',  # overwrite output file if exists
            output_path
        ]

        self.logger.info(f"Extracting first frame from remote URL to {output_path}")

        def run_ffmpeg():
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                raise Exception(f"ffmpeg failed: {result.stderr}")
            return output_path

        result = await asyncio.get_event_loop().run_in_executor(None, run_ffmpeg)

        if not os.path.exists(output_path):
            raise Exception(f"ffmpeg did not create output file: {output_path}")

        self.logger.info(f"Successfully created webp thumbnail: {output_path}")
        return result

    async def create_first_frame_webp(self, video_path: str, output_path: Optional[str] = None) -> str:
        """
        Creates a webp file from the first frame of an mp4 video.
        
        Args:
            video_path: Path to the mp4 video file
            output_path: Optional path for the resulting webp file. If not provided,
                         will use the same location as the video with .webp extension
        
        Returns:
            Path to the generated webp file

        Raises:
            FileNotFoundError: If the video file doesn't exist
            Exception: If there's an error processing the video
        """
        try:
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")

            if output_path is None:
                # Replace .mp4 extension with .webp
                base_path = os.path.splitext(video_path)[0]
                output_path = f"{base_path}.webp"
            
            # Use MoviePy to get the first frame, disable audio processing and set target resolution
            self.logger.info(f"Extracting first frame from {video_path}")
            clip = VideoFileClip(video_path, audio=False, target_resolution=(None, 1080))

            try:
                # Get the first frame at t=0 (or slightly after to avoid potential issues with t=0)
                frame = clip.get_frame(0)
                
                # Convert the numpy array to a PIL Image
                img = Image.fromarray(frame)
                
                # Save the image as webp
                img.save(output_path, 'webp', quality=85, method=6)
                
                self.logger.info(f"Successfully created webp thumbnail: {output_path}")
                return output_path
            finally:
                clip.close()

        except Exception as e:
            self.logger.error(f"Error creating webp thumbnail for {video_path}: {str(e)}")
            raise
    
    @staticmethod
    def _generate_clyppy_id(input_str: str, length: int = None, low_collision=True) -> str:
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

        # Convert to base36/62 (lowercase letters + numbers)
        # First convert hex to int, then to base36
        hash_int = int(hash_hex, 16)
        if low_collision:
            base = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
            if length is None: length = 10
        else:
            base = '0123456789abcdefghijklmnopqrstuvwxyz'
            if length is None: length = 8
        base_str = ''

        while hash_int:
            hash_int, remainder = divmod(hash_int, 62 if low_collision else 36)
            base_str = base[remainder] + base_str
        # Take first 'length' characters, pad with 'a' if too short
        result = base_str[:length]
        if len(result) < length:
            result = result + 'a' * (length - len(result))
        return result


class BaseMisc(ABC):
    def __init__(self, bot):
        self.logger = logging.getLogger(__name__)
        self.platform_name = None
        self.is_nsfw = False
        self.dl_timeout_secs = 600  # 10 min bc why not
        self.bot = bot
        self.cdn_client = bot.cdn_client

    @abstractmethod
    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'BaseClip':
        ...

    @abstractmethod
    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
        @param url: The url of the video
        @param extended_url_formats: (deprecated) if True, will allow to parse non-platform urls (ie fixupx/<post_id> would work for x.com/<post_id>)
        """
        ...

    def is_clip_link(self, url: str) -> bool:
        """
            Checks if a URL is a valid link format.
        """
        return bool(self.parse_clip_url(url))

    async def get_len(self, url: str, cookies=False, download=False) -> Optional[Union[float, LocalFileInfo]]:
        """
            Uses yt-dlp to check video length of the provided url
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'verbose': False,
            'extract_flat': not download,  # only extract metadata, (it won't download if this is true)
            'user_agent': YT_DLP_USER_AGENT
        }
        if cookies:
            fetch_cookies(ydl_opts, self.logger)

        if download:
            # Add max filesize option when downloading
            ydl_opts['max_filesize'] = YT_DLP_MAX_FILESIZE

        try:
            # Run yt-dlp in an executor to avoid blocking
            def get_duration() -> Optional[Union[float, LocalFileInfo]]:
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
                        raise DefinitelyNoDuration
                    else:
                        return info.get('duration', 0)

            duration = await asyncio.get_event_loop().run_in_executor(
                None, get_duration
            )
            return duration
        except Exception as e:
            self.logger.error(f"Error downloading video for {url}: {str(e)}")
            handle_yt_dlp_err(str(e))

    @staticmethod
    def is_dl_server(guild):
        if guild is None:
            return False
        elif str(guild.id) == str(DL_SERVER_ID):
            return True
        return False

    async def is_shortform(self, url: str, basemsg: Union[Message, SlashContext], cookies=False) -> tuple[bool, int, int]:
        try:
            d = await self.get_len(url, cookies)
        except NoDuration:
            # DefinitelyNoDuration will raise out of this - won't manually check
            d = None

        if d is None or d == 0:
            # yt-dlp unable to fetch duration directly, need to download the file to verify manually
            self.logger.info(f"yt-dlp unable to fetch duration for {url}, downloading to verify...")
            file = await self.get_len(url, cookies, download=True)
            self.logger.info(f'Downloaded {file.local_file_path} from {url} to verify...')
            d = file.duration

        return await author_has_enough_tokens(basemsg, d, url)


class BaseAutoEmbed:
    def __init__(self, platform: BaseMisc):
        self.bot = platform.bot
        self.is_base = False
        self.platform = platform
        self.logger = platform.logger
        self.embedder = AutoEmbedder(
            bot=self.bot,
            platform_tools=self.platform,
            logger=self.logger
        )
        self.OTHER_TXT_COMMANDS = {
            ".help": self.send_help,
            ".tokens": self.tokens_cmd,
            ".vote": self.vote_cmd
        }

    async def handle_message(self, event: MessageCreate, skip_check: bool = False, url: str = None):
        if skip_check and url:
            # URL already extracted from reply-to mode, skip validation
            await self.command_embed(
                ctx=event.message,
                url=url,
                platform=self.platform,
                slug=self.platform.parse_clip_url(url)
            )
        else:
            # Original logic - check if message is .embed command
            message_is_embed_command = (
                    event.message.content.startswith(f"{EMBED_TXT_COMMAND} ")  # support text command (!embed url)
                    and self.platform.is_clip_link(event.message.content.split(" ")[1])
            )
            if message_is_embed_command:
                await self.command_embed(
                    ctx=event.message,
                    url=event.message.content.split(" ")[1],  # the second word is the url
                    platform=self.platform,
                    slug=self.platform.parse_clip_url(event.message.content.split(" ")[-1])
                )
            else:
                # Platform-specific quickembed check happens inside on_message_create
                await self.embedder.on_message_create(event)

    @staticmethod
    async def _handle_timeout(ctx: SlashContext, url: str, amt: int):
        """Handle timeout for embed processing"""
        await asyncio.sleep(amt)

        # will be cancelled early if main execution finished before the sleep
        await ctx.send(
            content=f"The timeout of {amt // 60}m was reached when trying to download `{url}`, please try again later...",
            components=create_nexus_comps()
        )

    @staticmethod
    async def fetch_tokens(user):
        url = 'https://clyppy.io/api/tokens/get/'
        headers = {
            'X-API-Key': os.getenv('clyppy_post_key'),
            'Content-Type': 'application/json'
        }
        j = {'userid': user.id, 'username': user.username}
        async with get_aiohttp_session() as session:
            async with session.get(url, json=j, headers=headers) as response:
                if response.status == 200:
                    j = await response.json()
                    return j['tokens']
                else:
                    error_data = await response.json()
                    raise Exception(f"Failed to fetch user's VIP tokens: {error_data.get('error', 'Unknown error')}")

    async def send_help(self, ctx: Union[SlashContext, Message]):
        pre, cmds = "/", ""
        if isinstance(ctx, Message):
            ctx.send = ctx.reply
            pre, cmds = ".", ("Available commands: `.help`, `.vote`, `.tokens`, `.embed url`,\n"
                              "For a better experience, remember to give me permission to use slash commands!\n\n")

        about = "Clyppy converts video links into native Discord embeds! Share videos from YouTube, Twitch, Reddit, and more directly in chat.\n\n" + cmds
        about += (
            f"Use `/settings quickembed=True` and I will automatically respond to Twitch clips. Many other platforms are easily accessibly through the `{pre}embed` command\n\n"
            f"---------------------------------\n"
            f"- Join my [Discord server]({SUPPORT_SERVER_URL}) to be a part of the community!\n"
            f"- Star me on [GitHub]({GITHUB_URL}) to stay updated :)")
        help_embed = Embed(title="ABOUT CLYPPY", description=about)
        help_embed.footer = f"CLYPPY v{VERSION}"
        await ctx.send(
            content="Clyppy is a social bot that makes sharing videos easier!",
            embed=help_embed,
            components=create_nexus_comps()
        )
        await send_webhook(
            title=f'{"DM" if ctx.guild is None else ctx.guild.name} - {pre}help called',
            load=f"response - success",
            color=COLOR_GREEN,
            url=APPUSE_LOG_WEBHOOK,
            logger=self.logger
        )

    async def tokens_cmd(self, ctx: Union[SlashContext, Message]):
        pre = '/'
        if isinstance(ctx, Message):
            ctx.send = ctx.reply
            ctx.user = ctx.author
            pre = '.'

        tokens = await self.bot.base_embedder.fetch_tokens(ctx.user)
        await ctx.send(
            content=f"**You have `{tokens}` VIP tokens**\nUse your VIP tokens to embed longer videos!\n\n"
                    f"You can gain more by **voting** with `{pre}vote`",
            components=[
                Button(style=ButtonStyle.LINK, label="Vote!", url=CLYPPY_VOTE_URL),
                Button(style=ButtonStyle.LINK, label="View VIP Token History", url="https://clyppy.io/profile/tokens/history/")
            ]
        )
        await send_webhook(
            title=f'{"DM" if ctx.guild is None else ctx.guild.name}, {ctx.author.username} - {pre}tokens called',
            load=f"response - {tokens} tokens",
            color=COLOR_GREEN,
            url=APPUSE_LOG_WEBHOOK,
            logger=self.logger
        )

    async def vote_cmd(self, ctx: Union[SlashContext, Message]):
        pre = '/'
        if isinstance(ctx, Message):
            ctx.send = ctx.reply
            ctx.user = ctx.author
            pre = '.'

        msg = (f"**Vote for Clyppy!**\n"
               f"Give Clyppy your support by voting in popular bot sites!\n"
               f"By voting, receive the following benefits:\n\n"
               f"- Exclusive role in our Discord\n"
               f"- 1 free VIP token per vote!\n"
               f"- VIP tokens allow you to embed videos longer than the standard {MAX_VIDEO_LEN_SEC // 60} minutes!\n\n"
               f"You can get some free tokens by voting below, or purchasing them in bulk from our store `(づ๑•ᴗ•๑)づ♡`")
        await ctx.send(content=msg, components=[
            Button(style=ButtonStyle(ButtonStyle.LINK), label="Vote!", url=CLYPPY_VOTE_URL),
            Button(style=ButtonStyle(ButtonStyle.LINK), label="Buy in Bulk", url=BUY_TOKENS_URL)
        ])
        await send_webhook(
            title=f'{"DM" if ctx.guild is None else ctx.guild.name} - {ctx.user.username} - {pre}vote called',
            load=f"response - success",
            color=COLOR_GREEN,
            url=APPUSE_LOG_WEBHOOK,
            logger=self.logger
        )

    async def command_embed(self, ctx: Union[Message, SlashContext], url: str, platform, slug, extend_with_ai=False):
        async def wait_for_download(clip_id: str, timeout: float = 30):
            start_time = time()
            while clip_id in self.bot.currently_downloading:
                if time() - start_time > timeout:
                    raise TimeoutError(f"Waiting for clip {clip_id} download timed out")
                await asyncio.sleep(0.1)

        pre = "/"
        if isinstance(ctx, SlashContext):
            await ctx.defer(ephemeral=False)
        elif isinstance(ctx, Message):
            pre = "."
            ctx.send = ctx.reply
            ctx.user = ctx.author

        if ctx.guild:
            guild = GuildType(ctx.guild.id, ctx.guild.name, False)
            ctx_link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}"
            if Permissions.SEND_MESSAGES not in ctx.channel.permissions_for(ctx.guild.me):
                return None
            elif Permissions.READ_MESSAGE_HISTORY not in ctx.channel.permissions_for(ctx.guild.me) and isinstance(ctx, Message):
                return await ctx.send(
                    content=f"I don't have the permission `Read Message History` in this channel, which is required for text commands",
                    components=create_nexus_comps()
                )
            elif Permissions.EMBED_LINKS not in ctx.channel.permissions_for(ctx.guild.me):
                return await ctx.send(
                    content=f"I don't have permission to embed links in this channel",
                    components=create_nexus_comps()
                )
            if Permissions.SEND_MESSAGES_IN_THREADS not in ctx.channel.permissions_for(ctx.guild.me):
                if isinstance(ctx.channel, TYPE_THREAD_CHANNEL):
                    return None
        else:
            guild = GuildType(ctx.author.id, ctx.author.username, True)
            ctx_link = f"https://discord.com/channels/@me/{ctx.bot.user.id}"

        p = platform.platform_name if platform is not None else None
        try:
            self.logger.info(f"/{'extend' if extend_with_ai else 'embed'} in {guild.name} {url} -> {p}, {slug}")
            if guild.is_dm:
                nsfw_enabed = True
            elif isinstance(ctx.channel, TYPE_THREAD_CHANNEL):
                nsfw_enabed = ctx.channel.parent_channel.nsfw
            else:
                nsfw_enabed = ctx.channel.nsfw

            if platform is None:
                self.logger.info(f"return incompatible for /{'extend' if extend_with_ai else 'embed'} {url}")
                await ctx.send(
                    content=f"Couldn't {'extend' if extend_with_ai else 'embed'} that url (invalid/incompatible)",
                    components=create_nexus_comps()
                )
                await send_webhook(
                    title=f'{"DM" if guild.is_dm else guild.name} - {pre}{'extend' if extend_with_ai else 'embed'} called - Failure',
                    load=f"user - {ctx.user.username}\n"
                         f"cmd - {pre}{'extend' if extend_with_ai else 'embed'} url:{url}\n"
                         f"platform: {p}\n"
                         f"slug: {slug}\n"
                         f"response - Incompatible",
                    color=COLOR_RED,
                    url=APPUSE_LOG_WEBHOOK,
                    logger=self.logger
                )
                return None
            elif platform.is_nsfw and not nsfw_enabed:
                await ctx.send(
                    f"( ͡~ ͜ʖ ͡°) This platform is not allowed in this channel. You can either:\n"
                    f" - If you're a server admin, go to `Edit Channel > Overview` and toggle `Age-Restricted Channel`\n"
                    f" - If you're not an admin, you can invite me to one of your servers, and then create a new age-restricted channel there\n"
                    f"\n**Note** for iOS users, due to the Apple Store's rules, you may need to access [discord.com]({ctx_link}) in your phone's browser to enable this.\n"
                )
                await send_webhook(
                    title=f'{"DM" if guild.is_dm else guild.name} - {pre}{'extend' if extend_with_ai else 'embed'} called - Failure',
                    load=f"user - {ctx.user.username}\n"
                         f"cmd - {pre}{'extend' if extend_with_ai else 'embed'} url:{url}\n"
                         f"platform: {p}\n"
                         f"slug: {slug}\n"
                         f"response - NSFW disabled",
                    color=COLOR_RED,
                    url=APPUSE_LOG_WEBHOOK,
                    logger=self.logger
                )
                return None

            if self.bot.currently_embedding_users.count(ctx.user.id) >= 2:
                await ctx.send(f"You're already embedding 2 videos. Please wait for one to finish before trying again.")
                await send_webhook(
                    title=f'{"DM" if guild.is_dm else guild.name} - {pre}{'extend' if extend_with_ai else 'embed'} called - Failure',
                    load=f"user - {ctx.user.username}\n"
                         f"cmd - {pre}{'extend' if extend_with_ai else 'embed'} url:{url}\n"
                         f"platform: {p}\n"
                         f"slug: {slug}\n"
                         f"response - Already embedding",
                    color=COLOR_RED,
                    url=APPUSE_LOG_WEBHOOK,
                    logger=self.logger
                )
                return None
            else:
                self.bot.currently_embedding_users.append(ctx.user.id)

            if slug in self.bot.currently_downloading:
                try:
                    # if its already downloading from another embed command running at the same time
                    await wait_for_download(slug, timeout=platform.dl_timeout_secs)
                except TimeoutError:
                    pass  # continue with the dl anyway
            else:
                self.bot.currently_downloading.append(slug)
        except Exception as e:
            self.logger.info(f"Exception in /{'extend' if extend_with_ai else 'embed'} preparation: {str(e)}")
            await ctx.send(
                content=f"Unexpected error while trying to {'extend' if extend_with_ai else 'embed'} this url. Please **report** this error by joining our [Support Server]({SUPPORT_SERVER_URL})",
                components=create_nexus_comps()
            )
            await send_webhook(
                title=f'{"DM" if guild.is_dm else guild.name} - {pre}{'extend' if extend_with_ai else 'embed'} called - Failure',
                load=f"user - {ctx.user.username}\n"
                     f"cmd - {pre}{'extend' if extend_with_ai else 'embed'} url:{url}\n"
                     f"platform: {p}\n"
                     f"slug: {slug}\n"
                     f"response - Unexpected error",
                color=COLOR_RED,
                url=APPUSE_LOG_WEBHOOK,
                logger=self.logger
            )
            try:
                while slug in self.bot.currently_downloading:
                    self.bot.currently_downloading.remove(slug)
            except ValueError:
                pass
            try:
                while ctx.user.id in self.bot.currently_embedding_users:
                    self.bot.currently_embedding_users.remove(ctx.user.id)
            except ValueError:
                pass
            try:
                if isinstance(ctx, Message):
                    del self.embedder.clip_id_msg_timestamps[ctx.id]
            except KeyError:
                pass
            return None

        timeout_task = asyncio.create_task(self._handle_timeout(
            ctx=ctx,
            url=url,
            amt=platform.dl_timeout_secs
        ))
        main_task = asyncio.create_task(self._main_embed_task(
            ctx=ctx,
            url=url,
            platform=platform,
            slug=slug,
            platform_name=p,
            guild=guild,
            extend_with_ai=extend_with_ai
        ))
        done, pending = await asyncio.wait(
            [main_task, timeout_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        try:
            for task in done:
                # This will re-raise any exceptions that occurred in the task
                await task
        except Exception as e:
            # Log any unexpected exceptions not handled in the tasks themselves
            self.logger.info(f"/{'extend' if extend_with_ai else 'embed'} Task exception: {str(e)}")
        finally:
            try:
                while slug in self.bot.currently_downloading:
                    self.bot.currently_downloading.remove(slug)
            except ValueError:
                pass
            try:
                while ctx.user.id in self.bot.currently_embedding_users:
                    self.bot.currently_embedding_users.remove(ctx.user.id)
            except ValueError:
                pass
            try:
                if isinstance(ctx, Message):
                    del self.embedder.clip_id_msg_timestamps[ctx.id]
            except KeyError:
                pass

    async def _main_embed_task(
            self,
            ctx: Union[Message, SlashContext],
            url: str, slug: str, platform: BaseMisc,
            platform_name: str, guild: GuildType,
            extend_with_ai: bool = False
    ):
        user_tokens = None
        pre = "/"
        if isinstance(ctx, Message):
            pre = '.'

        response_msg = f"Unknown error in /{'extend' if extend_with_ai else 'embed'}"
        success, response, err_handled = False, "Timeout reached", False
        clip = None
        try:
            if isinstance(ctx, SlashContext):
                self.embedder.platform_tools = platform  # if called from /embed, the self.embedder is 'base'
            elif isinstance(ctx, Message):
                # for logging response times - it hasn't been set up for slash commands yet
                self.embedder.clip_id_msg_timestamps[ctx.id] = datetime.now().timestamp()

            clip = await self.embedder.platform_tools.get_clip(url, extended_url_formats=True, basemsg=ctx)

            if extend_with_ai:
                can_extend, tokens_used, user_tokens = await author_has_enough_tokens_for_ai_extend(ctx, clip.url)
                if not can_extend:
                    comp = [
                        Button(style=ButtonStyle(ButtonStyle.LINK), label="Free Tokens", url=CLYPPY_VOTE_URL),
                        Button(style=ButtonStyle(ButtonStyle.LINK), label="Buy Tokens", url=BUY_TOKENS_URL)
                    ]
                    if user_tokens is None: user_tokens = await self.fetch_tokens(ctx.user)
                    response_msg = f"{get_random_face()} You don't have enough tokens for that! You need at least {AI_EXTEND_TOKENS_COST}, but have {user_tokens}."
                    asyncio.create_task(ctx.send(response_msg, components=comp))
                    success, response, err_handled = False, "InsufficientTokens", True
                    raise ExceptionHandled

            await self.embedder.process_clip_link(
                clip=clip,
                clip_link=url,
                respond_to=ctx,
                guild=guild,
                try_send_files=True,
                extend_with_ai=extend_with_ai
            )
            success, response = True, "Success"
        except FileNotFoundError:  # ytdlp failed to download the file, but the output wasn't captured
            response_msg = f"The file could not be downloaded. Does the url points to a video?"
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "FileNotFound", True
        except IPBlockedError:
            response_msg = f"{get_random_face()} The platform said my IP was blocked from viewing that link"
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "IPBlocked", True
        except VideoUnavailable:
            response_msg = f"That video is not available anymore {get_random_face()}"
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "VideoUnavailable", True
        except VideoSaidUnavailable:
            response_msg = f"The url returned 'Video Unavailable'. It could be the wrong url, or maybe it's just not available in my region {get_random_face()}"
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "VideoUnavailable", True
        except RemoteTimeoutError:
            response_msg = f"The url returned 'Timeout Error'. Maybe there's an issue with the site at the moment... {get_random_face()}"
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "RemoteTimeout", True
        except UrlUnparsable:
            response_msg = f"I couldn't parse that url. Did you enter it correctly?"
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "UrlParseError", True
        except YtDlpForbiddenError:
            response_msg = f"I couldn't download that video file (Error 403 Forbidden). Maybe try again later, or use a different hosting website?"
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "403 Forbidden", True
        except UnsupportedError:
            response_msg = f"Couldn't {'extend' if extend_with_ai else 'embed'} that url. That platform is not supported {get_random_face()}"
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "Incompatible", True
        except (NoDuration, DefinitelyNoDuration):
            response_msg = f"Couldn't {'extend' if extend_with_ai else 'embed'} that url (not a video post)"
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "No duration", True
        except InvalidFileType:
            response_msg = f"Couldn't {'extend' if extend_with_ai else 'embed'} that url (invalid type/corrupted video file)"
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "Invalid file type", True
        except NoPermsToView:
            response_msg = f"Couldn't {'extend' if extend_with_ai else 'embed'} that url (no permissions to view)"
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "No permissions", True
        except (VideoTooLong, VideoLongerThanMaxLength) as e:
            if user_tokens is None: user_tokens = await self.fetch_tokens(ctx.user)
            dur = e.video_dur
            comp = [
                Button(style=ButtonStyle(ButtonStyle.LINK), label="Buy Tokens", url=BUY_TOKENS_URL),
                Button(style=ButtonStyle(ButtonStyle.LINK), label="Free Tokens (Vote)", url=CLYPPY_VOTE_URL),
                Button(style=ButtonStyle(ButtonStyle.LINK), label="Free Tokens (Join Discord)", url=SUPPORT_SERVER_URL),
            ]
            if dur >= EMBED_TOTAL_MAX_LENGTH:
                response_msg = f"{get_random_face()} I can't embed videos longer than {EMBED_TOTAL_MAX_LENGTH // (60 * 60)} hours total, even with Clyppy VIP Tokens."
                asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            elif 0 < user_tokens < (video_cost := get_token_cost(dur)):
                # the user has tokens available & the video_dur says it can be embedded with tokens, but the embed still reported too long
                response_msg = f"""{get_random_face()} This video was too long to embed ({dur / 60:.1f} minutes)\n
You can normally use `{pre}embed` on videos under {MAX_VIDEO_LEN_SEC / 60} minutes, but 
every {EMBED_TOKEN_COST} token can add {EMBED_W_TOKEN_MAX_LEN / 60} minutes of video time.\n
You have `{user_tokens}` tokens available.\n
Since it's {dur / 60:.1f} minutes long, it would cost `{video_cost}` VIP tokens."""
                asyncio.create_task(ctx.send(response_msg, components=comp))
            else:
                response_msg = f"""{get_random_face()}\nThis video was too long to embed (longer than {MAX_VIDEO_LEN_SEC / 60} minutes)
Voting with `/vote` will increase it by {EMBED_W_TOKEN_MAX_LEN // 60} minutes per vote!"""
                asyncio.create_task(ctx.send(content=response_msg, components=[
                    Button(style=ButtonStyle(ButtonStyle.LINK), label="Buy Tokens", url=BUY_TOKENS_URL),
                    Button(style=ButtonStyle(ButtonStyle.LINK), label="Free Tokens (Vote)", url=CLYPPY_VOTE_URL),
                    Button(style=ButtonStyle(ButtonStyle.LINK), label="Free Tokens (Join Discord)", url=SUPPORT_SERVER_URL),
                ]))
            success, response, err_handled = False, "Video too long", True
        except VideoContainsNSFWContent as e:
            reason = e.reason if hasattr(e, 'reason') else "inappropriate content detected"
            response_msg = f"{get_random_face()} I can't extend this video because it contains NSFW content.\n\nReason: {reason}"
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "VideoContainsNSFWContent", True
        except VideoTooLongForExtend:
            response_msg = f"{get_random_face()} I can't extend videos longer than {MAX_VIDEO_LEN_FOR_EXTEND} seconds."
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "VideoTooLongForExtend", True
        except VideoTooShortForExtend:
            response_msg = f"{get_random_face()} I can't extend videos shorter than {MIN_VIDEO_LEN_FOR_EXTEND} seconds."
            asyncio.create_task(ctx.send(response_msg, components=create_nexus_comps()))
            success, response, err_handled = False, "VideoTooShortForExtend", True
        except VideoExtensionFailed as e:
            response_msg = type(e).__name__ + ": " + str(e)
            self.logger.info(f'VideoExtensionFailed error in /{'extend' if extend_with_ai else 'embed'}: {response_msg}')

            # Extract just the error message, not all the script output
            error_text = str(e)

            # Try to parse JSON error format from the script
            try:
                import json
                # Look for "Fatal error: {" and extract JSON from there
                if "Fatal error: {" in error_text:
                    # Find the start of the JSON (after "Fatal error: ")
                    json_start = error_text.find("Fatal error: {") + len("Fatal error: ")
                    json_text = error_text[json_start:]

                    # Parse the JSON
                    error_data = json.loads(json_text)
                    error_text = error_data.get('error', error_text)
            except:
                pass  # If JSON parsing fails, use the full error text

            # Trim error message to 500 chars to avoid Discord's 2000 char limit
            if len(error_text) > 500:
                error_text = error_text[:497] + "..."

            asyncio.create_task(ctx.send(f"The video-generator API refused to create a video from your input: \n\n```{error_text}```",
                                         components=create_nexus_comps()))
            success, response, err_handled = False, "VideoExtensionFailed", True
        except ExceptionHandled:
            # just used as a goto
            pass
        except Exception as e:
            response_msg = type(e).__name__ + ": " + str(e)
            self.logger.info(f'Unexpected error in /{'extend' if extend_with_ai else 'embed'}: {response_msg}')
            asyncio.create_task(ctx.send(f"An unexpected error occurred with your input `{url}`",
                           components=create_nexus_comps()))
            success, response, err_handled = False, "Unexpected error", False

        finally:
            if clip is not None:
                url_str = clip.clyppy_url if not clip.is_discord_attachment else "`discord upload`"
            else:
                url_str = "`error`"
            asyncio.create_task(send_webhook(
                title=f'{"DM" if guild.is_dm else guild.name} - {pre}{'extend' if extend_with_ai else 'embed'} called - {"Success" if success else "Failure"}',
                load=f"user - {ctx.user.username}\n"
                     f"cmd - `{pre}{'extend' if extend_with_ai else 'embed'} url:{url}`\n"
                     f"platform: {platform_name}\n"
                     f"slug: {slug}\n"
                     f"URL: {url_str}\n"
                     f"response - {response}",
                color=COLOR_GREEN if success else COLOR_RED,
                embed=False,
                url=APPUSE_LOG_WEBHOOK,
                logger=self.logger
            ))
            if not success:
                exception = {
                    'name': response,
                    'msg': response_msg
                }
                asyncio.create_task(push_interaction_error(
                    parent_msg=ctx,
                    platform_name=platform_name,
                    clip=clip,
                    clip_url=url,
                    error_info=exception,
                    handled=err_handled,
                    logger=self.logger
                ))
