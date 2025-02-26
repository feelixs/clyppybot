import re
from bot.classes import BaseClip, BaseMisc, VideoTooLong, NoDuration, DownloadResponse
from typing import Optional


class InstagramMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Instagram"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
        Extracts the Instagram Reel shortcode from various URL formats.
        Returns None if the URL is not a valid Instagram Reel URL.
        """
        # Matches URLs like:
        # - https://www.instagram.com/reel/Cq8YJ3sJzHk/
        # - https://instagram.com/reel/Cq8YJ3sJzHk
        # - https://www.instagram.com/reel/Cq8YJ3sJzHk/?hl=en
        patterns = [
            r'(?:https?://)?(?:www\.)?instagram\.com/reel/([a-zA-Z0-9_-]+)(?:/|$|\?)',
            r'(?:https?://)?(?:www\.)?instagram.com/share/r/([a-zA-Z0-9_-]+)(?:/|$|\?)'
        ]
        for p in patterns:
            match = re.match(p, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=True) -> 'InstagramClip':
        shortcode = self.parse_clip_url(url)
        if not shortcode:
            self.logger.info(f"Invalid Instagram URL: {url}")
            raise NoDuration

        # Verify video length (Reels are up to 90 seconds)
        valid = await self.is_shortform(
            url=url,
            basemsg=basemsg,
            cookies=cookies
        )
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        return InstagramClip(shortcode)


class InstagramClip(BaseClip):
    def __init__(self, shortcode):
        self._service = "instagram"
        self._shortcode = shortcode
        super().__init__(shortcode)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return f"https://www.instagram.com/reel/{self._shortcode}/"

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=True) -> DownloadResponse:
        self.logger.info(f"({self.id}) run dl_check_size()...")
        dl = await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies
        )
        if dl is not None:
            return dl

        return await super().download(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies
        )
