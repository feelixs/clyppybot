from bot.platforms.medal import MedalClip
from bot.classes import BaseMisc
import re
from typing import Optional


class MedalMisc(BaseMisc):
    def __init__(self, bot):
        super().__init__(bot)
        self.platform_name = "Medal"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
        Parses a Medal.tv clip URL to extract just the clip ID.

        Example:
        "https://medal.tv/games/game/clips/abc123/xyz789" -> "abc123"
        "https://medal.tv/clips/abc123" -> "abc123"
        """
        patterns = [
            # Full game path pattern
            r'^(?:https?://)?(?:www\.)?medal\.tv/games/[\w-]+/clips/([\w-]+)',
            # Short clip pattern
            r'^(?:https?://)?(?:www\.)?medal\.tv/clips/([\w-]+)'
        ]

        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> MedalClip:
        slug = self.parse_clip_url(url)
        return MedalClip(slug, self.cdn_client)