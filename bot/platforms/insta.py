import re
import asyncio
import time
from bot.classes import BaseClip, BaseMisc
from bot.errors import VideoTooLong, NoDuration
from bot.types import DownloadResponse
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

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=True) -> DownloadResponse:
        # Rate limiting: ensure minimum delay between Instagram requests
        current_time = time.time()
        time_since_last = current_time - self.misc.last_request_time

        if time_since_last < self.misc.min_delay:
            delay = self.misc.min_delay - time_since_last
            self.logger.info(f"Rate limiting: waiting {delay:.1f}s before Instagram request")
            await asyncio.sleep(delay)

        self.misc.last_request_time = time.time()
        self.logger.info(f"({self.id}) run dl_check_size()...")

        # Add Instagram-specific headers to avoid detection
        extra_opts = {
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'TE': 'trailers'
            }
        }

        dl = await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies,
            extra_opts=extra_opts
        )
        if dl is not None:
            return dl

        return await super().download(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies,
            extra_opts=extra_opts
        )
