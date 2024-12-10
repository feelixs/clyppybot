from typing import Optional
import logging
from bot.kick import KickClip
import re


class KickMisc:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.platform_name = "Kick"

    @staticmethod
    def parse_clip_url(url: str) -> (str, str):
        user = url.split('kick.com/')[-1].split("/")[0]
        if url.endswith("/"):
            url = url[:-1]  # remove trailing slash
        slug = str(url).split('/')[-1]
        if "?clip=" in slug:
            slug = slug.split("=")[-1]
        elif "?" in slug:
            slug = slug.split('?')[0]
        slug = slug.replace("clip_", "")
        return slug, user

    @staticmethod
    def is_clip_link(url: str) -> bool:
        # Pattern matches both:
        # https://kick.com/clip/[clip-id]
        # https://kick.com/[username]/clip/[clip-id]
        clip_pattern = r'https?://kick\.com/[a-zA-Z0-9-_]+/clips/[a-zA-Z0-9_]+(?:[A-Z0-9]+)?'
        query_pattern = r'https?://kick\.com/[a-zA-Z0-9-_]+\?clips=[a-zA-Z0-9_]+(?:[A-Z0-9]+)?'
        return bool(re.match(clip_pattern, url) or re.match(query_pattern, url))

    async def get_clip(self, url: str) -> KickClip:
        slug, user = self.parse_clip_url(url)
        return KickClip(slug, user)
