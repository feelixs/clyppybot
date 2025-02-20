from bot.classes import BaseMisc
from bot.platforms.kick import KickClip
from typing import Optional
import re


class KickMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Kick"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
            Extracts the video ID from a YouTube URL if present.
            Works with all supported URL formats.
        """
        # Common YouTube URL patterns
        patterns = [
            r'^https?://(?:www\.)?kick\.com/[a-zA-Z0-9_-]+/clips/clip_[a-zA-Z0-9]+',
            r'^https?://(?:www\.)?kick\.com/[a-zA-Z0-9_-]+\?clip=clip_[a-zA-Z0-9]+'
        ]
        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(2)
        return None

    def get_clip_user(self, url: str) -> Optional[str]:
        patterns = [
            r'^https?://(?:www\.)?kick\.com/[a-zA-Z0-9_-]+/clips/clip_[a-zA-Z0-9]+',
            r'^https?://(?:www\.)?kick\.com/[a-zA-Z0-9_-]+\?clip=clip_[a-zA-Z0-9]+'
        ]
        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None) -> KickClip:
        slug, user = self.parse_clip_url(url)
        return KickClip(slug, user)
