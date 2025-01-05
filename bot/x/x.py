import logging
import yt_dlp
import asyncio
import os
import re
from bot.classes import BaseClip, BaseMisc


class Xmisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Twitter"
        self.silence_invalid_url = True

    def parse_clip_url(self, url: str) -> str:
        """
        Extracts the tweet ID/slug from various Twitter URL formats.
        Returns None if the URL is not a valid Twitter URL.
        """
        patterns = [
            r'twitter\.com/\w+/status/(\d+)',
            r'x\.com/\w+/status/(\d+)',
            r't\.co/(\w+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str) -> 'Xclip':
        slug = self.parse_clip_url(url)
        valid = await self.is_shortform(url)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            return None
        self.logger.info(f"{url} is_shortform=True")

        return Xclip(slug)


class Xclip(BaseClip):
    def __init__(self, slug, user):
        super().__init__(slug)
        self.service = "twitter"
        self.url = f"https://x.com/{user}/status/{slug}"
