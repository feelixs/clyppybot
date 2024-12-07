from .api import TwitchAPI
from typing import Optional
import logging
from bot.twitch.twitchclip import TwitchClip
from os import getenv, path
import re


class TwitchMisc:
    def __init__(self, **kwargs):
        self.logger = logging.getLogger(__name__)
        tid = getenv("CLYPP_TWITCH_ID")
        if tid is None:
            exit("No Twitch API key found")
        tis = getenv("CLYPP_TWITCH_SECRET")
        if tis is None:
            exit("No Twitch API secret found")
        self.platform_name = "Twitch"
        self.api = TwitchAPI(key=tid, secret=tis,
                             logger=self.logger,
                             log_path=path.join('logs', 'twitch-api-usage.log'))

    @staticmethod
    def parse_clip_url(url: str) -> str:
        if url.endswith("/"):
            url = url[:-1]  # remove trailing slash

        if "m.twitch.tv" in url:
            # convert mobile link to pc link
            url = url.replace("https://m.", "https://clips.").replace("/clip/", "/").split("?")[0]
        slug = str(url).split('/')[-1]
        if "?" in slug:
            slug = slug.split('?')[0]
        return slug

    @staticmethod
    def is_clip_link(url: str) -> bool:
        patterns = [
            r'https?://(?:www\.|m\.)?clips\.twitch\.tv/[a-zA-Z0-9_-]+',
            r'https?://(?:www\.|m\.)?twitch\.tv/(?:[a-zA-Z0-9_-]+/)?clip/[a-zA-Z0-9_-]+'
        ]
        return any(re.match(pattern, url) for pattern in patterns)

    async def get_clip(self, url: str) -> Optional[TwitchClip]:
        slug = self.parse_clip_url(url)
        info = await self.api.get("https://api.twitch.tv/helix/clips?id=" + slug)
        try:
            return TwitchClip(info['data'][0], self.api)
        except IndexError:
            return None
