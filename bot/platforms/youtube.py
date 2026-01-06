from bot.errors import InvalidClipType, VideoTooLong
from bot.classes import BaseClip, BaseMisc
from bot.types import DownloadResponse
from bot.env import YT_DLP_USER_AGENT
from yt_dlp import YoutubeDL
from typing import Optional
import asyncio
import re


class YtMisc(BaseMisc):
    def __init__(self, bot):
        super().__init__(bot)
        self.platform_name = "YouTube"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
            Extracts the video ID from a YouTube URL if present.
            Works with all supported URL formats.
        """
        # Common YouTube URL patterns
        patterns = [
            r'^(?:https?://)?(?:(?:www|m)\.)?(?:youtube\.com/(?:[^/]+/.+/|(?:v|e(?:mbed)?)/|.*[?&]v=)|youtu\.be/)([^"&?/ ]{11})',
            r'^(?:https?://)?(?:(?:www|m)\.)?(?:youtube\.com/shorts/)([^"&?/ ]{11})',
            r'^(?:https?://)?(?:(?:www|m)\.)?youtube\.com/clip/([^"&?/ ]{11})'
        ]
        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=True) -> 'YtClip':
        slug = self.parse_clip_url(url)
        if slug is None:
            raise InvalidClipType
        if "&list=" in url:
            url = url.split("&list=")[0]
        valid, tokens_used, duration = await self.is_shortform(
            url=url,
            basemsg=basemsg,
            cookies=cookies
        )
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong(duration)
        self.logger.info(f"{url} is_shortform=True")
        return YtClip(slug, bool(re.search(r'youtube\.com/shorts/', url)), self.cdn_client, tokens_used, duration)


class YtClip(BaseClip):
    def __init__(self, slug, short, cdn_client, tokens_used: int, duration: int):
        self._service = "youtube"
        if short:
            self._url = f"https://youtube.com/shorts/{slug}"
        else:
            self._url = f"https://youtube.com/watch/?v={slug}"
        super().__init__(slug, cdn_client, tokens_used, duration)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    @property
    def clyppy_url(self) -> str:
        """Use /e/ path for YouTube redirect-based embeds"""
        return f"https://clyppy.io/e/{self.clyppy_id}"

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=True, extra_opts=None) -> DownloadResponse:
        """
        Extract CDN URL and create a redirect-based embed.
        No video download needed - Discord follows the redirect to YouTube CDN.
        """
        self.logger.info(f"({self.id}) run dl_check_size(upload_if_large=False)...")
        local_file = await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies,
            upload_if_large=False
        )
        if local_file is not None and local_file.can_be_discord_uploaded:
            return local_file

        # Ensure clyppy_id is set
        if self.clyppy_id is None:
            await self.compute_clyppy_id()

        # Extract CDN URL without downloading
        cdn_url, info = await self._extract_cdn_url(dlp_format, cookies)

        self.logger.info(f"({self.id}) Extracted CDN URL, returning DownloadResponse")

        return DownloadResponse(
            remote_url=cdn_url,
            local_file_path=None,
            duration=self.duration,  # Already set from is_shortform()
            width=dict(info).get('width') or 0,
            height=dict(info).get('height') or 0,
            filesize=dict(info).get('filesize') or 0,
            video_name=info.get('title'),
            can_be_discord_uploaded=False,
            clyppy_object_is_stored_as_redirect=True
        )

    async def _extract_cdn_url(self, dlp_format='best/bv*+ba', cookies=True):
        """Extract the CDN URL without downloading."""
        ydl_opts = {
            'format': dlp_format,
            'quiet': True,
            'no_warnings': True,
            'user_agent': YT_DLP_USER_AGENT
        }
        if cookies:
            ydl_opts['cookiefile'] = 'cookies.txt'

        def extract():
            with YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(self.url, download=False)

        info = await asyncio.get_event_loop().run_in_executor(None, extract)

        cdn_url = info.get('url')
        if not cdn_url:
            raise Exception("Failed to extract CDN URL from YouTube video")

        return cdn_url, info
