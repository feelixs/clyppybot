from bot.classes import BaseMisc
from bot.types import DownloadResponse
from bot.classes import BaseClip
from bot.io import get_aiohttp_session
from yt_dlp import YoutubeDL
from bot.env import YT_DLP_USER_AGENT
from typing import Optional
import asyncio
import re
import os
import time


class TwitchMisc(BaseMisc):
    def __init__(self, bot):
        super().__init__(bot)
        self.always_embed = True
        self.platform_name = "Twitch"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
            Extracts the video ID from a Twitch URL if present.
            Works with all supported URL formats.
        """
        patterns = [
            r'^(?:https?://)?(?:www\.|m\.)?clips\.twitch\.tv/([a-zA-Z0-9_-]+)(?:\?.*)?$',
            r'^(?:https?://)?(?:www\.|m\.)?twitch\.tv/(?:[a-zA-Z0-9_-]+/)?clip/([a-zA-Z0-9_-]+)(?:\?.*)?$',
            r'^(?:https?://)?(?:www\.)?clyppy\.com/?clips/([a-zA-Z0-9_-]+)',
            r'^(?:https?://)?(?:www\.)?clyppy\.io/?clips/([a-zA-Z0-9_-]+)'
        ]
        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'TwitchClip':
        slug = self.parse_clip_url(url)
        return TwitchClip(slug, self.cdn_client, 0)


class TwitchClip(BaseClip):
    def __init__(self, slug, cdn_client, tokens_used: int):
        self._service = "twitch"
        self._url = f"https://clips.twitch.tv/{slug}"
        # pass dummy duration because we know twitch clips will never need to use vip tokens
        super().__init__(slug, cdn_client, tokens_used, 0)
        self._thumbnail_url = None

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    @property
    def clyppy_url(self) -> str:
        """Use /embed/ path for Twitch redirect-based embeds"""
        return f"https://clyppy.io/e/{self.clyppy_id}"

    async def get_thumbnail(self):
        return self._thumbnail_url

    async def download(self, filename=None, dlp_format='best', can_send_files=False, cookies=False) -> DownloadResponse:
        """
        Extract direct CDN URL and create a redirect-based embed.
        No video download needed - Discord follows the redirect to the CDN.
        """
        self.logger.info(f"({self.id}) run dl_check_size(upload_if_large=False)...")
        dl = await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies,
            upload_if_large=False
        )
        if dl is not None and dl.can_be_discord_uploaded:
            return dl

        # Ensure clyppy_id is set
        if self.clyppy_id is None:
            await self.compute_clyppy_id()

        # Extract video info and determine URL type
        is_permanent, cdn_url, info = await self._extract_cdn_url(dlp_format)

        # Set expiry for temporary URLs (~10 hours from now)
        expires_at = None
        if not is_permanent:
            expires_at = int(time.time()) + (10 * 60 * 60)  # 10 hours

        # Call clyppy.io API to create the redirect entry
        api_url = "https://clyppy.io/api/create/redirect/"
        headers = {
            'X-API-Key': os.getenv('clyppy_post_key'),
            'Content-Type': 'application/json'
        }
        payload = {
            'url': cdn_url,
            'service': 'twitch',
            'clip_id': self.clyppy_id,
            'original_url': self.url,
            'expires_at': expires_at
        }

        async with get_aiohttp_session() as session:
            async with session.post(api_url, json=payload, headers=headers) as response:
                if response.status in [200, 201]:
                    result = await response.json()
                    self.logger.info(f"Created Twitch redirect entry: {result}")
                else:
                    error_text = await response.text()
                    self.logger.error(f"Failed to create Twitch redirect: {response.status} - {error_text}")
                    raise Exception(f"Failed to create Twitch redirect: {error_text}")

        # Return DownloadResponse with the embed URL
        embed_url = f"https://clyppy.io/e/{self.clyppy_id}"
        self.logger.info(f"({self.id}) Returning embed URL: {embed_url} (permanent={is_permanent})")

        return DownloadResponse(
            remote_url=cdn_url,
            local_file_path=None,
            duration=info.get('duration') or 0,
            width=dict(info).get('width') or 0,
            height=dict(info).get('height') or 0,
            filesize=dict(info).get('filesize') or 0,
            video_name=info.get('title'),
            can_be_discord_uploaded=False
        )

    async def _extract_cdn_url(self, dlp_format='best'):
        """
        Extract the CDN URL without downloading.
        Returns: (is_permanent, cdn_url, info_dict)
        """
        ydl_opts = {
            'format': dlp_format,
            'quiet': True,
            'no_warnings': True,
            'user_agent': YT_DLP_USER_AGENT
        }

        def extract():
            with YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(self.url, download=False)

        info = await asyncio.get_event_loop().run_in_executor(None, extract)

        self._thumbnail_url = info.get('thumbnail')

        # Check if this is a permanent media-assets2 URL
        if self._thumbnail_url and '/clips-media-assets2.twitch.tv/' in self._thumbnail_url:
            self.logger.info(f"{self.id} is permanent media-assets2 type")
            mp4_url = re.sub(r'-preview-\d+x\d+\.jpg$', '.mp4', self._thumbnail_url)
            return True, mp4_url, info

        # Otherwise use the temporary URL from yt-dlp
        cdn_url = info.get('url')
        if not cdn_url:
            raise Exception("Failed to extract CDN URL from Twitch clip")

        self.logger.info(f"{self.id} is temporary URL type (expires in ~10hrs)")
        return False, cdn_url, info
