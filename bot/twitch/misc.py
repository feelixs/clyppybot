from typing import Optional
from bot.twitch.twitchclip import TwitchClip
from os import getenv
import re
from bot.classes import BaseMisc


class TwitchMisc(BaseMisc):
    def __init__(self, **kwargs):
        super().__init__()
        tid = getenv("CLYPP_TWITCH_ID")
        if tid is None:
            exit("No Twitch API key found")
        tis = getenv("CLYPP_TWITCH_SECRET")
        if tis is None:
            exit("No Twitch API secret found")
        self.platform_name = "Twitch"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> str:
        if url.endswith("/"):
            url = url[:-1]  # remove trailing slash

        if "m.twitch.tv" in url:
            # convert mobile link to pc link
            url = url.replace("https://m.", "https://clips.").replace("/clip/", "/").split("?")[0]
        slug = str(url).split('/')[-1]
        if "?" in slug:
            slug = slug.split('?')[0]
        return slug
    
    def is_clip_link(self, url: str) -> bool:
        patterns = [
            r'https?://(?:www\.|m\.)?clips\.twitch\.tv/[a-zA-Z0-9_-]+',
            r'https?://(?:www\.|m\.)?twitch\.tv/(?:[a-zA-Z0-9_-]+/)?clip/[a-zA-Z0-9_-]+',
            r'https?://(?:www\.)?clyppy\.com/?clips/[a-zA-Z0-9_-]+',
            r'https?://(?:www\.)?clyppy\.io/?clips/[a-zA-Z0-9_-]+'
        ]
        return any(re.match(pattern, url) for pattern in patterns)

    async def get_clip(self, url: str, extended_url_formats=False) -> Optional[TwitchClip]:
        slug = self.parse_clip_url(url)
        return TwitchClip(slug)
