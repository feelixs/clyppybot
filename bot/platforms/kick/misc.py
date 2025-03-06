from bot.classes import BaseMisc
from bot.platforms.kick import KickClip
from typing import Optional
import re


class KickMisc(BaseMisc):
    def __init__(self, bot):
        super().__init__(bot)
        self.platform_name = "Kick"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
        Extracts the clip ID from a Kick URL if present.
        Works with all supported URL formats.
        """
        patterns = [
            r'^(?:https?://)?(?:www\.)?kick\.com/[a-zA-Z0-9_-]+/clips/clip_([a-zA-Z0-9]+)',
            r'^(?:https?://)?(?:www\.)?kick\.com/[a-zA-Z0-9_-]+\?clip=clip_([a-zA-Z0-9]+)'
        ]
        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def get_clip_user(url: str) -> Optional[str]:
        patterns = [
            r'^(?:https?://)?(?:www\.)?kick\.com/([a-zA-Z0-9_-]+)/clips/clip_[a-zA-Z0-9]+',
            r'^(?:https?://)?(?:www\.)?kick\.com/([a-zA-Z0-9_-]+)\?clip=clip_[a-zA-Z0-9]+'
        ]
        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> KickClip:
        slug, user = self.parse_clip_url(url), self.get_clip_user(url)
        return KickClip(slug, user, self.cdn_client)
