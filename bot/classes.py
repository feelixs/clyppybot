from bot.env import MAX_FILE_SIZE_FOR_DISCORD, YT_DLP_USER_AGENT
from bot.io import author_has_enough_tokens, author_has_premium
from abc import ABC, abstractmethod
from yt_dlp import YoutubeDL
from typing import Optional, Union
from moviepy.video.io.VideoFileClip import VideoFileClip
from interactions import Message, SlashContext, TYPE_THREAD_CHANNEL, Embed, Permissions
from interactions.api.events import MessageCreate
from bot.io.cdn import CdnSpacesClient
from bot.io import get_aiohttp_session
from bot.tools.embedder import AutoEmbedder
from bot.types import LocalFileInfo, DownloadResponse, GuildType, COLOR_GREEN, COLOR_RED
from bot.env import (EMBED_TXT_COMMAND, create_nexus_str, APPUSE_LOG_WEBHOOK, EMBED_TOKEN_COST, MAX_VIDEO_LEN_SEC,
                     EMBED_W_TOKEN_MAX_LEN, LOGGER_WEBHOOK, SUPPORT_SERVER_URL, VERSION, TOPGG_VOTE_LINK, DL_SERVER_ID,
                     INFINITY_VOTE_LINK, DLIST_VOTE_LINK)
from bot.errors import NoDuration, UnknownError, UploadFailed, NoPermsToView, VideoTooLong, ClipFailure, IPBlockedError, \
    InvalidFileType, UnsupportedError, YtDlpForbiddenError, UrlUnparsable, VideoSaidUnavailable, handle_yt_dlp_err
from PIL import Image
import hashlib
import aiohttp
from datetime import datetime
import logging
import asyncio
from time import time
import random
import os


def tryremove(f):
    try:
        os.remove(f)
    except:
        pass


def get_random_face():
    faces = ['`(⌯˃̶᷄ ﹏ ˂̶᷄⌯)`', 'ヽ(゜～゜o)ノ', '( ͡ಠ ͜ʖ ͡ಠ)', '(╯°□°)╯︵ ┻━┻', '乁( ⁰͡ Ĺ̯ ⁰͡ ) ㄏ']
    return f'{random.choice(faces)}'

def is_discord_compatible(filesize: float):
    if filesize is None:
        return False
    return MAX_FILE_SIZE_FOR_DISCORD > filesize > 0


async def send_webhook(logger, content: Optional[str] = None, title: Optional[str] = None, load: Optional[str] = None, url: Optional[str]=None, color=None, in_test=False):
    if not in_test and os.getenv("TEST"):
        return

    if url is None:
        url = LOGGER_WEBHOOK

    # Create a rich embed
    if color is None:
        color = 5814783  # Blue color

    e = []
    if title is not None and load is not None:
        e = [{
                "title": title,
                "description": load,
                "color": color,
            }]

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
                    """Helper to extract format details with safe defaults"""
                    return {
                        'url': fmt.get('url', ''),
                        'width': fmt.get('width', w or 1280),
                        'height': fmt.get('height', h or 720),
                    }

                # Try to get direct URL first
                if 'url' in info and info['url']:
                    # Handle special cases for known platforms
                    if "production.assets.clips.twitchcdn.net" in info['url']:
                        self.logger.info("Using default dimensions for Twitch clip")
                        format_info = extract_format_info(info, h=720, w=1280)
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
                        can_be_discord_uploaded=None
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
                            can_be_discord_uploaded=None
                        )

                # If we get here, no suitable format was found
                self.logger.error(f"No suitable format found in info: {info.keys()}")
                raise ValueError("No playable formats found")

            except Exception as e:
                self.logger.error(f"Error extracting info for {self.url}: {str(e)}")
                raise

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
                    can_be_discord_uploaded=True
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
            'user_agent': YT_DLP_USER_AGENT
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

    async def _fetch_file(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False) -> LocalFileInfo:
        local_file = await self.dl_download(filename, dlp_format, can_send_files, cookies)
        if local_file is None:
            raise UnknownError
        return local_file

    async def dl_check_size(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, upload_if_large=False, cookies=False) -> Optional[DownloadResponse]:
        """
            Download the clip file, and return the local file info if its within Discord's file size limit,
            otherwise return None
        """
        local = None
        if can_send_files:
            local = await self._fetch_file(filename, dlp_format, can_send_files, cookies)
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
                    can_be_discord_uploaded=True
                )

        if upload_if_large:
            if local is None:
                local = await self._fetch_file(filename, dlp_format, can_send_files, cookies)
            self.logger.info(f"{self.id} is too large to upload to discord, uploading to clyppy.io instead...")
            return await self.upload_to_clyppyio(local)

        return None

    async def dl_download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False) -> Optional[LocalFileInfo]:
        if os.path.isfile(filename):
            self.logger.info("file already exists! returning...")
            return get_video_details(filename)

        ydl_opts = {
            'format': dlp_format,
            'outtmpl': filename,
            'quiet': True,
            'no_warnings': True,
            'user_agent': YT_DLP_USER_AGENT
        }

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
                can_be_discord_uploaded=None
            )
        else:
            self.logger.error(f"Failed to upload video: {remote_url}")
            raise UploadFailed

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
    def __init__(self, bot):
        self.logger = logging.getLogger(__name__)
        self.platform_name = None
        self.always_embed = False  # are quickembeds enabled for this platform?
        self.is_nsfw = False
        self.dl_timeout_secs = 120
        self.bot = bot
        self.cdn_client = bot.cdn_client

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

    async def get_len(self, url: str, cookies=False, download=False) -> Union[float, LocalFileInfo]:
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

        return await author_has_enough_tokens(basemsg, d, url)


class BaseAutoEmbed:
    def __init__(self, platform: BaseMisc, always_embed=False):
        self.bot = platform.bot
        self.is_base = False
        self.always_embed_this_platform = always_embed
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

    async def handle_message(self, event: MessageCreate):
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
        elif self.platform.is_dl_server(event.message.guild) or self.platform.always_embed:
            await self.embedder.on_message_create(event)

    @staticmethod
    async def _handle_timeout(ctx: SlashContext, url: str, amt: int):
        """Handle timeout for embed processing"""
        await asyncio.sleep(amt)

        # will be cancelled early if main execution finished before the sleep
        await ctx.send(f"The timeout of {amt // 60}m was reached when trying to download `{url}`, please try again later... {create_nexus_str()}")

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
            f"Use `/settings quickembed=True` and I will automatically respond to Twitch and Kick clips, and all other compatible platforms are only accessibly through `{pre}embed`\n\n"
            "**UPDATE Dec 3rd 2024** Clyppy is back online after a break. We are working on improving the service and adding new features. Stay tuned!\n\n"
            "**COMING SOON** We're working on adding server customization for Clyppy, so you can choose which platforms I will automatically reply to!\n\n"
            f"---------------------------------\n"
            f"Join my [Discord server]({SUPPORT_SERVER_URL}) for more info and to get updates!")
        help_embed = Embed(title="ABOUT CLYPPY", description=about)
        help_embed.description += create_nexus_str()
        help_embed.footer = f"CLYPPY v{VERSION}"
        await ctx.send(content="Clyppy is a social bot that makes sharing videos easier!", embed=help_embed)
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
        await ctx.send(f"You have `{tokens}` VIP tokens!\n"
                       f"You can gain more by **voting** with `{pre}vote`\n\n"
                       f"Use your VIP tokens to embed longer videos with Clyppy (up to {EMBED_W_TOKEN_MAX_LEN // 60} minutes!)")
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

        await ctx.send(embed=Embed(
            title="Vote for Clyppy!",
            description=f"Give Clyppy your support by voting in popular bot sites! By voting, receive the "
                        f"following benefits:\n\n"
                        f"- Exclusive role in [our Discord]({SUPPORT_SERVER_URL})\n"
                        f"- (2) VIP tokens per vote!\n"
                        f"- VIP tokens allow you to embed videos up to {EMBED_W_TOKEN_MAX_LEN // 60} minutes in length!\n\n"
                        f"View all the vote links below. Your support is appreciated.\n\n"
                        f"** - [Top.gg]({TOPGG_VOTE_LINK})**\n"
                        f"** - [InfinityBots]({INFINITY_VOTE_LINK})**\n"
                        f"** - [DiscordBotList]({DLIST_VOTE_LINK})**\n"
                        # f"** - [BotList.me]({BOTLISTME_VOTE_LINK})**"
                        f"\n\nYou can also purchase VIP tokens directly from the [Clyppy store](https://clyppy.io/profile/tokens/)\n\n"
                        f"{create_nexus_str()}"
        ))
        await send_webhook(
            title=f'{"DM" if ctx.guild is None else ctx.guild.name} - {ctx.user.username} - {pre}vote called',
            load=f"response - success",
            color=COLOR_GREEN,
            url=APPUSE_LOG_WEBHOOK,
            logger=self.logger
        )

    async def command_embed(self, ctx: Union[Message, SlashContext], url: str, platform, slug):
        async def wait_for_download(clip_id: str, timeout: float = 30):
            start_time = time()
            while clip_id in self.bot.currently_downloading:
                if time() - start_time > timeout:
                    raise TimeoutError(f"Waiting for clip {clip_id} download timed out")
                await asyncio.sleep(0.1)

        timeout_task = None

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
                return 1
            elif Permissions.READ_MESSAGE_HISTORY not in ctx.channel.permissions_for(ctx.guild.me) and isinstance(ctx, Message):
                return await ctx.send(f"I don't have the permission `Read Message History` in this channel, which is required for text commands {create_nexus_str()}")
            elif Permissions.EMBED_LINKS not in ctx.channel.permissions_for(ctx.guild.me):
                return await ctx.send(f"I don't have permission to embed links in this channel {create_nexus_str()}")
            if Permissions.SEND_MESSAGES_IN_THREADS not in ctx.channel.permissions_for(ctx.guild.me):
                if isinstance(ctx.channel, TYPE_THREAD_CHANNEL):
                    return 1
        else:
            guild = GuildType(ctx.author.id, ctx.author.username, True)
            ctx_link = f"https://discord.com/channels/@me/{ctx.bot.user.id}"

        p = platform.platform_name if platform is not None else None
        try:
            self.logger.info(f"/embed in {guild.name} {url} -> {p}, {slug}")

            if guild.is_dm:
                nsfw_enabed = True
            elif isinstance(ctx.channel, TYPE_THREAD_CHANNEL):
                nsfw_enabed = ctx.channel.parent_channel.nsfw
            else:
                nsfw_enabed = ctx.channel.nsfw

            if platform is None:
                self.logger.info(f"return incompatible for /embed {url}")
                await ctx.send(f"Couldn't embed that url (invalid/incompatible) {create_nexus_str()}")
                await send_webhook(
                    title=f'{"DM" if guild.is_dm else guild.name} - {pre}embed called - Failure',
                    load=f"user - {ctx.user.username}\n"
                         f"cmd - {pre}embed url:{url}\n"
                         f"platform: {p}\n"
                         f"slug: {slug}\n"
                         f"response - Incompatible",
                    color=COLOR_RED,
                    url=APPUSE_LOG_WEBHOOK,
                    logger=self.logger
                )
                return
            elif platform.is_nsfw and not nsfw_enabed:
                await ctx.send(f"( ͡~ ͜ʖ ͡°) This platform is not allowed in this channel. You can either:\n"
                               f" - If you're a server admin, go to `Edit Channel > Overview` and toggle `Age-Restricted Channel`\n"
                               f" - If you're not an admin, you can invite me to one of your servers, and then create a new age-restricted channel there\n"
                               f"\n**Note** for iOS users, due to the Apple Store's rules, you may need to access [discord.com]({ctx_link}) in your phone's browser to enable this.\n")
                await send_webhook(
                    title=f'{"DM" if guild.is_dm else guild.name} - {pre}embed called - Failure',
                    load=f"user - {ctx.user.username}\n"
                         f"cmd - {pre}embed url:{url}\n"
                         f"platform: {p}\n"
                         f"slug: {slug}\n"
                         f"response - NSFW disabled",
                    color=COLOR_RED,
                    url=APPUSE_LOG_WEBHOOK,
                    logger=self.logger
                )
                return

            if self.bot.currently_embedding_users.count(ctx.user.id) >= 2:
                await ctx.send(f"You're already embedding 2 videos. Please wait for one to finish before trying again.")
                await send_webhook(
                    title=f'{"DM" if guild.is_dm else guild.name} - {pre}embed called - Failure',
                    load=f"user - {ctx.user.username}\n"
                         f"cmd - {pre}embed url:{url}\n"
                         f"platform: {p}\n"
                         f"slug: {slug}\n"
                         f"response - Already embedding",
                    color=COLOR_RED,
                    url=APPUSE_LOG_WEBHOOK,
                    logger=self.logger
                )
                return
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
            self.logger.info(f"Exception in /embed preparation: {str(e)}")
            await ctx.send(f"Unexpected error while trying to embed this url {create_nexus_str()}")
            await send_webhook(
                title=f'{"DM" if guild.is_dm else guild.name} - {pre}embed called - Failure',
                load=f"user - {ctx.user.username}\n"
                     f"cmd - {pre}embed url:{url}\n"
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
            return

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
            guild=guild
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
            self.logger.info(f"/embed Task exception: {str(e)}")
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

    async def _main_embed_task(self, ctx: Union[Message, SlashContext], url: str, slug: str, platform: BaseMisc, platform_name: str, guild: GuildType):
        pre = "/"
        if isinstance(ctx, Message):
            pre = '.'

        success, response = False, "Timeout reached"
        try:
            if isinstance(ctx, SlashContext):
                self.embedder.platform_tools = platform  # if called from /embed, the self.embedder is 'base'
            elif isinstance(ctx, Message):
                # for logging response times - it hasn't been set up for slash commands yet
                self.embedder.clip_id_msg_timestamps[ctx.id] = datetime.now().timestamp()

            await self.embedder._process_this_clip_link(
                clip_link=url,
                respond_to=ctx,
                guild=guild,
                try_send_files=True
            )
            success, response = True, "Success"
        except FileNotFoundError:  # ytdlp failed to download the file, but the output wasn't captured
            await ctx.send(f"The file could not be downloaded. Does the url points to a video? {create_nexus_str()}")
            success, response = False, "FileNotFound"
        except IPBlockedError:
            await ctx.send(f"{get_random_face()} The platform said my IP was blocked from viewing that link {create_nexus_str()}")
            success, response = False, "IPBlocked"
        except VideoSaidUnavailable:
            await ctx.send(f"The url returned 'Video Unavailable'. It could be the wrong url, or maybe it's just not available in my region `'(ᗒᗣᗕ)՞` {create_nexus_str()}")
            success, response = False, "VideoUnavailable"
        except UrlUnparsable:
            await ctx.send(f"I couldn't parse that url. Did you enter it correctly? {create_nexus_str()}")
            success, response = False, "UrlParseError"
        except YtDlpForbiddenError:
            await ctx.send(f"I couldn't download that video file (Error 403 Forbidden). Maybe try again later, or use a different hosting website? {create_nexus_str()}")
            success, response = False, "403 Forbidden"
        except UnsupportedError:
            await ctx.send(f"Couldn't embed that url (invalid/incompatible) {create_nexus_str()}")
            success, response = False, "Incompatible"
        except NoDuration:
            await ctx.send(f"Couldn't embed that url (not a video post) {create_nexus_str()}")
            success, response = False, "No duration"
        except InvalidFileType:
            await ctx.send(f"Couldn't embed that url (invalid type/corrupted video file) {create_nexus_str()}")
            success, response = False, "Invalid file type"
        except NoPermsToView:
            await ctx.send(f"Couldn't embed that url (no permissions to view) {create_nexus_str()}")
            success, response = False, "No permissions"
        except VideoTooLong:
            if await self.fetch_tokens(ctx.user) >= EMBED_TOKEN_COST:
                await ctx.send(f"{get_random_face()} This video was too long to embed (longer than {MAX_VIDEO_LEN_SEC / 60} minutes)\n"
                               f"It's also longer than {EMBED_W_TOKEN_MAX_LEN // 60} minutes, so using your VIP tokens wouldn't work either...")
            else:
                await ctx.send(f"{get_random_face()} This video was too long to embed (longer than {MAX_VIDEO_LEN_SEC / 60} minutes)\n"
                               f"Voting with `/vote` will increase it to {EMBED_W_TOKEN_MAX_LEN // 60} minutes! {create_nexus_str()}")
            success, response = False, "Video too long"
        except ClipFailure:
            await ctx.send(f"Unexpected error while trying to download this clip {create_nexus_str()}")
            success, response = False, "Clip failure"
        except Exception as e:
            self.logger.info(f'Unexpected error in /embed: {str(e)}')
            await ctx.send(f"An unexpected error occurred with your input `{url}` {create_nexus_str()}")
            success, response = False, "Unexpected error"

        finally:
            await send_webhook(
                title=f'{"DM" if guild.is_dm else guild.name} - {pre}embed called - {"Success" if success else "Failure"}',
                load=f"user - {ctx.user.username}\n"
                     f"cmd - {pre}embed url:{url}\n"
                     f"platform: {platform_name}\n"
                     f"slug: {slug}\n"
                     f"response - {response}",
                color=COLOR_GREEN if success else COLOR_RED,
                url=APPUSE_LOG_WEBHOOK,
                logger=self.logger
            )
