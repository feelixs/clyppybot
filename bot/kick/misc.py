from typing import Optional
import logging
from bot.kick import KickClip
import re


class KickMisc:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.platform_name = "Kick"

    @staticmethod
    def parse_clip_url(url: str) -> tuple[str, str]:
        # Match both standard and query parameter formats
        if "?clip=" in url:
            # Handle format: kick.com/username?clip=clip_ID
            user = url.split('kick.com/')[-1].split('?')[0]
            slug = url.split('?clip=')[-1]
        else:
            # Handle format: kick.com/username/clips/clip_ID
            user = url.split('kick.com/')[-1].split("/")[0]
            if url.endswith("/"):
                url = url[:-1]
            slug = str(url).split('/')[-1]
            if "?" in slug:
                slug = slug.split('?')[0]

        # Clean up the values
        if user.endswith('/'):
            user = user[:-1]
        slug = slug.replace("clip_", "")

        return slug, user

    @staticmethod
    def is_clip_link(url: str) -> bool:
        kick_clip_patterns = [
            # Standard clip URL format
            r'^https?://(?:www\.)?kick\.com/(?:(?:clips/clip_)|(?:[^/]+/clips/clip_))[\w-]+$',
            # Query parameter format
            r'^https?://(?:www\.)?kick\.com/[^/]+\?clip=clip_[\w-]+$'
        ]
        return any(bool(re.match(pattern, url)) for pattern in kick_clip_patterns)

    async def get_clip(self, url: str) -> 'KickClip':
        slug, user = self.parse_clip_url(url)
        return KickClip(slug, user)
