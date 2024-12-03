from .api import TwitchAPI
from typing import Optional
import logging
from bot.twitch.clip import Clip
from os import getenv, path


class TwitchMisc:
    def __init__(self, **kwargs):
        self.logger = logging.getLogger(__name__)
        tid = getenv("CLPP_TWITCH_ID")
        if tid is None:
            exit("No Twitch API key found")
        tis = getenv("TWITCH_CLYPP_SECRET")
        if tis is None:
            exit("No Twitch API secret found")
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
    def is_twitch_clip_link(message: str):
        "https://clips.twitch.tv/BombasticSuccessfulMonitorSoonerLater-19gZfam5vc-A5CFh"
        return message.startswith("https://www.twitch.tv/") or message.startswith("https://www.m.twitch.tv/") \
            or message.startswith("https://twitch.tv/") or message.startswith("https://m.twitch.tv/") \
            or message.startswith("https://clips.twitch.tv/") or message.startswith("https://m.clips.twitch.tv/") \
            or message.startswith("https://www.clips.twitch.tv/") or message.startswith("https://www.m.clips.twitch.tv/")

    async def get_clip(self, url: str) -> Optional[Clip]:
        slug = self.parse_clip_url(url)
        info = await self.api.get("https://api.twitch.tv/helix/clips?id=" + slug)
        try:
            return Clip(info['data'][0], self.api)
        except IndexError:
            return None
