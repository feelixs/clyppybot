from typing import Optional
import logging
from bot.medal import MedalClip
import re


class MedalMisc:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.platform_name = "Medal"

    @staticmethod
    def parse_clip_url(url: str) -> Optional[str]:
        """
        Parses a Medal.tv clip URL to extract just the clip ID.

        Example:
        "https://medal.tv/games/game/clips/abc123/xyz789" -> "abc123"
        "https://medal.tv/clips/abc123" -> "abc123"
        """
        # Find the ID that comes after "clips/"
        match = re.search(r'clips/([\w-]+)', url)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def is_clip_link(url: str) -> bool:
        """
        Validates if a given URL is a valid Medal.tv clip link.
        """
        patterns = [
            # Full game path pattern
            r'^https?://(?:www\.)?medal\.tv/games/[\w-]+/clips/[\w-]+',
            # Short clip pattern
            r'^https?://(?:www\.)?medal\.tv/clips/[\w-]+'
        ]

        return any(bool(re.match(pattern, url)) for pattern in patterns)

    async def get_clip(self, url: str) -> MedalClip:
        slug = self.parse_clip_url(url)
        return MedalClip(slug)
