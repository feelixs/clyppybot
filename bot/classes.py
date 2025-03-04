from bot.env import DL_SERVER_ID, YT_DLP_USER_AGENT, LOGGER_WEBHOOK
from bot.io import author_has_enough_tokens
from abc import ABC, abstractmethod
from yt_dlp import YoutubeDL
from typing import Optional, Union, Tuple
from interactions import Message, SlashContext, TYPE_THREAD_CHANNEL
from yt_dlp.utils import DownloadError
from bot.io.cdn import CdnSpacesClient
from bot.io.io import get_aiohttp_session, fetch_cookies
from bot.types import LocalFileInfo, COLOR_RED, COLOR_GREEN, GuildType, BaseClipInterface, get_video_details
from bot.errors import NoDuration, NoPermsToView, VideoTooLong, ClipFailure
from bot.env import APPUSE_LOG_WEBHOOK, EMBED_TOKEN_COST, EMBED_W_TOKEN_MAX_LEN, MAX_VIDEO_LEN_SEC
from bot.tools.misc import create_nexus_str
import logging
import asyncio
from time import time
import os
import aiohttp
from bot.tools.embedder import AutoEmbedder


def compute_platform(url: str, bot) -> Tuple[Optional['BaseMisc'], Optional[str]]:
    """Determine the platform and clip ID from the URL"""
    for this_platform in bot.platform_list:
        if slug := this_platform.parse_clip_url(url):
            return this_platform, slug

    return None, None


async def send_webhook(title: str, load: str, color=None, url=None, in_test=False):
    if not in_test and os.getenv("TEST"):
        return

    if url is None:
        url = LOGGER_WEBHOOK

    # Create a rich embed
    if color is None:
        color = 5814783  # Blue color
    payload = {
        "embeds": [{
            "title": title,
            "description": load,
            "color": color,
        }]
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload) as response:
                if response.status == 204:
                    print(f"Successfully sent logger webhook: {load}")
                else:
                    print(f"Failed to send logger webhook. Status: {response.status}")
                return response.status
        except Exception as e:
            print(f"Error sending log webhook: {str(e)}")
            return None


def tryremove(f):
    try:
        os.remove(f)
    except:
        pass


class BaseClip(BaseClipInterface):
    """Base class for all clip types"""

    @abstractmethod
    def __init__(self, slug: str, cdn_client: CdnSpacesClient):
        super().__init__(slug, cdn_client)


class BaseMisc(ABC):
    def __init__(self, bot):
        self.logger = logging.getLogger(__name__)
        self.platform_name = None
        self.bot = bot
        self.is_nsfw = False
        self.dl_timeout_secs = 30
        self.cdn_client = bot.cdn_client
        self.currently_downloading_for_embed = []
        self.currently_embedding_users = []

    @abstractmethod
    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'BaseClip':
        ...

    @abstractmethod
    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        ...

    @staticmethod
    async def _handle_timeout(ctx: SlashContext, url: str, amt: int):
        """Handle timeout for embed processing"""
        await asyncio.sleep(amt)
        if not ctx.responded:
            await ctx.send(f"An error occurred with your input `{url}` {create_nexus_str()}")
            raise TimeoutError(f"Waiting for clip {url} download timed out")

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

    async def command_embed(self, ctx: Union[Message, SlashContext], url: str):
        async def wait_for_download(clip_id: str, timeout: float = 30):
            start_time = time()
            while clip_id in self.currently_downloading_for_embed:
                if time() - start_time > timeout:
                    raise TimeoutError(f"Waiting for clip {clip_id} download timed out")
                await asyncio.sleep(0.1)

        timeout_task = None
        if isinstance(ctx, SlashContext):
            await ctx.defer(ephemeral=False)
        elif isinstance(ctx, Message):
            ctx.send = ctx.reply

        if ctx.guild:
            guild = GuildType(ctx.guild.id, ctx.guild.name, False)
            ctx_link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}"
        else:
            guild = GuildType(ctx.author.id, ctx.author.username, True)
            ctx_link = f"https://discord.com/channels/@me/{ctx.bot.user.id}"

        slug, p = None, None
        try:
            if not url.startswith("https://"):
                url = "https://" + url
            platform, slug = compute_platform(url, self.bot)

            p = platform.platform_name if platform is not None else None
            self.logger.info(f"/embed in {guild.name} {url} -> {p}, {slug}")

            if guild.is_dm:
                nsfw_enabed = True
            elif isinstance(ctx.channel, TYPE_THREAD_CHANNEL):
                # GuildPublicThread has no attribute nsfw
                nsfw_enabed = False
            else:
                nsfw_enabed = ctx.channel.nsfw

            if platform is None:
                self.logger.info(f"return incompatible for /embed {url}")
                await ctx.send(f"Couldn't embed that url (invalid/incompatible) {create_nexus_str()}")
                await send_webhook(
                    title=f'{["DM" if guild.is_dm else guild.name]} - /embed called - Failure',
                    load=f"user - {ctx.user.username}\n"
                         f"cmd - /embed url:{url}\n"
                         f"platform: {p}\n"
                         f"slug: {slug}\n"
                         f"response - Incompatible",
                    color=COLOR_RED,
                    url=APPUSE_LOG_WEBHOOK
                )
                return
            elif platform.is_nsfw and not nsfw_enabed:
                await ctx.send(f"This platform is not allowed in this channel. You can either:\n"
                               f" - If you're a server admin, go to `Edit Channel > Overview` and toggle `Age-Restricted Channel`\n"
                               f" - If you're not an admin, you can invite me to one of your servers, and then create a new age-restricted channel there\n"
                               f"\n**Note** for iOS users, due to the Apple Store's rules, you may need to access [discord.com]({ctx_link}) in your phone's browser to enable this.\n")
                await send_webhook(
                    title=f'{["DM" if guild.is_dm else guild.name]} - /embed called - Failure',
                    load=f"user - {ctx.user.username}\n"
                         f"cmd - /embed url:{url}\n"
                         f"platform: {p}\n"
                         f"slug: {slug}\n"
                         f"response - NSFW disabled",
                    color=COLOR_RED,
                    url=APPUSE_LOG_WEBHOOK
                )
                return

            if ctx.user.id in self.currently_embedding_users:
                await ctx.send(f"You're already embedding a video. Please wait for it to finish before trying again.")
                await send_webhook(
                    title=f'{["DM" if guild.is_dm else guild.name]} - /embed called - Failure',
                    load=f"user - {ctx.user.username}\n"
                         f"cmd - /embed url:{url}\n"
                         f"platform: {p}\n"
                         f"slug: {slug}\n"
                         f"response - Already embedding",
                    color=COLOR_RED,
                )
                return
            else:
                self.currently_embedding_users.append(ctx.user.id)

            if slug in self.currently_downloading_for_embed:
                try:
                    # if its already downloading from another embed command running at the same time
                    await wait_for_download(slug, timeout=platform.dl_timeout_secs)
                except TimeoutError:
                    pass  # continue with the dl anyway
            else:
                self.currently_downloading_for_embed.append(slug)

            timeout_task = asyncio.create_task(self._handle_timeout(ctx, url, platform.dl_timeout_secs))
            e = AutoEmbedder(self.bot, platform, logging.getLogger(__name__))
        except Exception as e:
            if timeout_task is not None:
                timeout_task.cancel()
            self.logger.info(f"Exception in /embed: {str(e)}")
            await ctx.send(f"Unexpected error while trying to embed this url {create_nexus_str()}")
            await send_webhook(
                title=f'{["DM" if guild.is_dm else guild.name]} - /embed called - Failure',
                load=f"user - {ctx.user.username}\n"
                     f"cmd - /embed url:{url}\n"
                     f"platform: {p}\n"
                     f"slug: {slug}\n"
                     f"response - Unexpected error",
                color=COLOR_RED,
                url=APPUSE_LOG_WEBHOOK
            )
            return

        success, response = False, "Unknown error"
        try:
            await e._process_this_clip_link(
                clip_link=url,
                respond_to=ctx,
                guild=guild,
                try_send_files=True
            )
            success, response = True, "Success"
        except NoDuration:
            await ctx.send(f"Couldn't embed that url (not a video post) {create_nexus_str()}")
            success, response = False, "No duration"
        except NoPermsToView:
            await ctx.send(f"Couldn't embed that url (no permissions to view) {create_nexus_str()}")
            success, response = False, "No permisions"
        except VideoTooLong:
            if await self.fetch_tokens(ctx.user) >= EMBED_TOKEN_COST:
                await ctx.send(f"This video was too long to embed (longer than {MAX_VIDEO_LEN_SEC / 60} minutes)\n"
                               f"It's also longer than {EMBED_W_TOKEN_MAX_LEN // 60} minutes, so using your VIP tokens wouldn't work either...")
            else:
                await ctx.send(f"This video was too long to embed (longer than {MAX_VIDEO_LEN_SEC / 60} minutes)\n"
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
            timeout_task.cancel()

            await send_webhook(
                title=f'{["DM" if guild.is_dm else guild.name]} - /embed called - {["Success" if success else "Failure"]}',
                load=f"user - {ctx.user.username}\n"
                     f"cmd - /embed url:{url}\n"
                     f"platform: {p}\n"
                     f"slug: {slug}\n"
                     f"response - {response}",
                color=[COLOR_GREEN if success else COLOR_RED],
                url=APPUSE_LOG_WEBHOOK
            )
            try:
                self.currently_downloading_for_embed.remove(slug)
            except ValueError:
                pass
            try:
                self.currently_embedding_users.remove(ctx.user.id)
            except ValueError:
                pass

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

        except DownloadError as e:
            self.logger.error(f"Error downloading video for {url}: {str(e)}")
            if 'You don\'t have permission' in str(e) or "unable to view this" in str(e):
                raise NoPermsToView
            raise VideoTooLong
        except Exception as e:
            self.logger.error(f"Error checking video length for {url}: {str(e)}")
            if 'MoviePy error: failed to read the first frame of video file' in str(e):
                raise VideoTooLong
            raise NoDuration

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

        return await author_has_enough_tokens(basemsg, d)
