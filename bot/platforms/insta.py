import re
import os
from bot.classes import BaseClip, BaseMisc
from bot.errors import VideoTooLong, NoDuration
from bot.types import DownloadResponse
from bot.io import get_aiohttp_session
from typing import Optional


class InstagramMisc(BaseMisc):
    def __init__(self, bot):
        super().__init__(bot)
        self.platform_name = "Instagram"
        self.last_request_time = 0  # Track last Instagram request time
        self.min_delay = 5  # Minimum 5 seconds between requests

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
        Extracts the Instagram Reel shortcode from various URL formats.
        Returns None if the URL is not a valid Instagram Reel URL.
        """
        # Matches URLs like:
        # - https://www.instagram.com/reel/Cq8YJ3sJzHk/
        # - https://instagram.com/reel/Cq8YJ3sJzHk
        # - https://www.instagram.com/reel/Cq8YJ3sJzHk/?hl=en
        pattern = r'(?:https?://)?(?:www\.)?instagram\.com/reel/([a-zA-Z0-9_-]+)(?:/|$|\?)'
        match = re.match(pattern, url)
        return match.group(1) if match else None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=True) -> 'InstagramClip':
        shortcode = self.parse_clip_url(url)
        if not shortcode:
            self.logger.info(f"Invalid Instagram URL: {url}")
            raise NoDuration

        valid, tokens_used, duration = await self.is_shortform(
            url=url,
            basemsg=basemsg,
            cookies=cookies
        )
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong(duration)
        self.logger.info(f"{url} is_shortform=True")

        return InstagramClip(shortcode, self.cdn_client, tokens_used, duration, self)


class InstagramClip(BaseClip):
    def __init__(self, shortcode, cdn_client, tokens_used: int, duration: int, misc: InstagramMisc):
        self._service = "instagram"
        self._shortcode = shortcode
        self.misc = misc  # Reference to InstagramMisc for rate limiting
        super().__init__(shortcode, cdn_client, tokens_used, duration)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return f"https://www.instagram.com/reel/{self._shortcode}/"

    @property
    def clyppy_url(self) -> str:
        """Use /embed/ path for Instagram redirect-based embeds"""
        return f"https://clyppy.io/e/{self.clyppy_id}"

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=True, extra_opts=None) -> DownloadResponse:
        """
        Create a redirect-based embed for Instagram using kkinstagram.com.
        Instead of downloading the video, we create a clyppy.io/embed/<id> URL
        that redirects to kkinstagram, which then redirects to the Instagram CDN.
        """
        # Build the kkinstagram redirect URL
        kkinstagram_url = f"https://www.kkinstagram.com/reel/{self._shortcode}"
        self.logger.info(f"({self.id}) Creating redirect embed via kkinstagram: {kkinstagram_url}")

        # Ensure clyppy_id is set
        if self.clyppy_id is None:
            await self.compute_clyppy_id()

        # Call clyppy.io API to create the redirect entry
        api_url = "https://clyppy.io/api/create/redirect/"
        headers = {
            'X-API-Key': os.getenv('clyppy_post_key'),
            'Content-Type': 'application/json'
        }
        payload = {
            'url': kkinstagram_url,
            'service': 'instagram',
            'clip_id': self.clyppy_id,
            'original_url': self.url
        }

        async with get_aiohttp_session() as session:
            async with session.post(api_url, json=payload, headers=headers) as response:
                if response.status in [200, 201]:
                    result = await response.json()
                    self.logger.info(f"Created redirect entry: {result}")
                else:
                    error_text = await response.text()
                    self.logger.error(f"Failed to create redirect: {response.status} - {error_text}")
                    raise Exception(f"Failed to create Instagram redirect: {error_text}")

        # Return DownloadResponse with the embed URL
        embed_url = f"https://clyppy.io/embed/{self.clyppy_id}"
        self.logger.info(f"({self.id}) Returning embed URL: {embed_url}")

        return DownloadResponse(
            remote_url=embed_url,
            local_file_path=None,
            duration=self.duration,
            width=0,  # Unknown for redirect-based embeds
            height=0,
            filesize=0,
            video_name=None,
            can_be_discord_uploaded=False,
            override_show_download_button=False
        )
