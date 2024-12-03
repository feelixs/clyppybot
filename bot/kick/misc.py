from typing import Optional
import logging
from bot.kick import KickClip
import re


class KickMisc:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def parse_clip_url(url: str) -> str:
        if url.endswith("/"):
            url = url[:-1]  # remove trailing slash
        slug = str(url).split('/')[-1]
        if "?" in slug:
            slug = slug.split('?')[0]
        return slug

    @staticmethod
    def is_kick_clip_link(url: str) -> bool:
        # Pattern matches both:
        # https://kick.com/clip/[clip-id]
        # https://kick.com/[username]/clip/[clip-id]
        kick_clip_pattern = r'^https?://(?:www\.)?kick\.com/(?:(?:clip/)|(?:[^/]+/clip/))[\w-]+$'
        return bool(re.match(kick_clip_pattern, url))

    async def get_clip(self, url: str) -> KickClip:
        slug = self.parse_clip_url(url)
        return KickClip(slug)
