from bot.classes import BaseMisc
from bot.types import DownloadResponse
from bot.classes import BaseClip
from bot.errors import InvalidClipType
from yt_dlp import YoutubeDL
from bot.env import YT_DLP_USER_AGENT
from typing import Optional
import asyncio
import re


class TwitchMisc(BaseMisc):
    def __init__(self, bot):
        super().__init__(bot)
        self.always_embed = True
        self.platform_name = "Twitch"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
            Extracts the video ID from a YouTube URL if present.
            Works with all supported URL formats.
        """
        patterns = [
            r'^(?:https?://)?(?:www\.|m\.)?clips\.twitch\.tv/([a-zA-Z0-9_-]+)/?$',
            r'^(?:https?://)?(?:www\.|m\.)?twitch\.tv/(?:[a-zA-Z0-9_-]+/)?clip/([a-zA-Z0-9_-]+)/?$',
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
        super().__init__(slug, cdn_client, tokens_used)
        self._thumbnail_url = None

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def get_thumbnail(self):
        return self._thumbnail_url

    async def download(self, filename=None, dlp_format='best', can_send_files=False, cookies=False) -> DownloadResponse:
        dl = await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies
        )
        if dl is not None:
            return dl

        try:
            media_assets_url = self._get_direct_clip_url()
            ydl_opts = {
                'format': dlp_format,
                'quiet': True,
                'no_warnings': True,
                'user_agent': YT_DLP_USER_AGENT
            }
            extracted = await asyncio.get_event_loop().run_in_executor(
                None,
                self._extract_info,
                ydl_opts
            )
            extracted.remote_url = media_assets_url
            return extracted
        except InvalidClipType:
            # fetch temporary v2 link (default)
            return await super().download(
                filename=filename,
                dlp_format=dlp_format,
                can_send_files=can_send_files,
                cookies=cookies
            )

    def _get_direct_clip_url(self):
        # only works for some twitch clip links
        # for some reason only some twitch links are type media-assets2
        # and others use https://static-cdn.jtvnw.net/twitch-clips-thumbnails-prod/, which idk yet how to directly link the perm mp4 link
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'user_agent': YT_DLP_USER_AGENT
        }
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if not info.get('thumbnail'):
                    raise Exception("No thumbnail URL found in clip info")
                self._thumbnail_url = info['thumbnail']
                if '/clips-media-assets2.twitch.tv/' not in self._thumbnail_url:
                    raise InvalidClipType

                self.logger.info(f"{self.id} is of type media-assets2, parsing direct URL...")
                mp4_url = re.sub(r'-preview-\d+x\d+\.jpg$', '.mp4', self._thumbnail_url)
                return mp4_url
        except InvalidClipType:
            raise
        except Exception as e:
            raise Exception(f"Failed to extract clip URL: {str(e)}")
