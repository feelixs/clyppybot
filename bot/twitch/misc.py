from .api import TwitchAPI
from typing import Optional
import logging
from .clip import Clip
from os import getenv


class DriverDownloadFailed(Exception):
    pass


class ClipNotExists(Exception):
    pass


class TwitchMisc:
    def __init__(self, **kwargs):
        shard_id = kwargs['shard_id']
        if shard_id is None:
            shard_id = 'nan'
        self.logger = logging.getLogger("twitch")
        self.api = TwitchAPI(key=getenv("TWITCH_ID"), secret=getenv("TWITCH_SECRET"),
                             logger=self.logger,
                             log_path=getenv('TWITCH_API_REMAINING_LOG'),
                             log_name="twitch-api-usage_shard" + str(shard_id) + ".log")
        
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
