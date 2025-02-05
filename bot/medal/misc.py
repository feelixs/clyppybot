from typing import Optional
import logging
from bot.medal import MedalClip
from bot.classes import BaseMisc, InvalidClipType
import re


class MedalMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Medal"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
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

    def is_clip_link(self, url: str) -> bool:
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

    async def get_clip(self, url: str, extended_url_formats=False) -> MedalClip:
        slug = self.parse_clip_url(url)
        if slug is None:
            raise InvalidClipType
        return MedalClip(slug)
