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
        # First get the user
        user = url.split('kick.com/')[-1].split("?")[0]
        if user.endswith('/'):
            user = user[:-1]

        # Then extract the clip ID
        if "?clip=" in url:
            # Handle new format: kick.com/username?clip=clip_ID
            slug = url.split("?clip=")[-1]
        else:
            # Handle old format: kick.com/username/clips/clip_ID
            slug = url.split('/')[-1]

        # Clean up the slug
        if "?" in slug:
            slug = slug.split('?')[0]
        slug = slug.replace("clip_", "")

        return slug, user

    @staticmethod
    def is_clip_link(url: str) -> bool:
        kick_clip_patterns = [
            r'^https?://(?:www\.)?kick\.com/[^/]+\?clip=clip_[\w-]+',  # New format
            r'^https?://(?:www\.)?kick\.com/(?:clips/clip_)[\w-]+$',  # Direct clip link
            r'^https?://(?:www\.)?kick\.com/[^/]+/clips/clip_[\w-]+$'  # User clip link
        ]
        return any(bool(re.match(pattern, url)) for pattern in kick_clip_patterns)

    async def get_clip(self, url: str) -> 'KickClip':
        slug, user = self.parse_clip_url(url)
        return KickClip(slug, user)
