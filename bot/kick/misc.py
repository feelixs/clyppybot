from typing import Optional
import logging
from bot.kick import KickClip


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
    def is_twitch_clip_link(message: str):
        "https://clips.twitch.tv/BombasticSuccessfulMonitorSoonerLater-19gZfam5vc-A5CFh"
        return message.startswith("https://www.twitch.tv/") or message.startswith("https://www.m.twitch.tv/") \
            or message.startswith("https://twitch.tv/") or message.startswith("https://m.twitch.tv/") \
            or message.startswith("https://clips.twitch.tv/") or message.startswith("https://m.clips.twitch.tv/") \
            or message.startswith("https://www.clips.twitch.tv/") or message.startswith("https://www.m.clips.twitch.tv/")

    async def get_clip(self, url: str) -> KickClip:
        slug = self.parse_clip_url(url)
        return KickClip(slug)
