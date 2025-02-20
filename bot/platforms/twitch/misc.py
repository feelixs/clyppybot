from bot.platforms.twitch.twitchclip import TwitchClip
from os import getenv
import re
from bot.classes import BaseMisc
from typing import Optional


class TwitchMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        tid = getenv("CLYPP_TWITCH_ID")
        if tid is None:
            exit("No Twitch API key found")
        tis = getenv("CLYPP_TWITCH_SECRET")
        if tis is None:
            exit("No Twitch API secret found")
        self.platform_name = "Twitch"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
            Extracts the video ID from a YouTube URL if present.
            Works with all supported URL formats.
        """
        patterns = [
            r'^(?:https?://)?(?:www\.|m\.)?clips\.twitch\.tv/[a-zA-Z0-9_-]+',
            r'^(?:https?://)?(?:www\.|m\.)?twitch\.tv/(?:[a-zA-Z0-9_-]+/)?clip/[a-zA-Z0-9_-]+',
            r'^(?:https?://)?(?:www\.)?clyppy\.com/?clips/[a-zA-Z0-9_-]+',
            r'^(?:https?://)?(?:www\.)?clyppy\.io/?clips/[a-zA-Z0-9_-]+'
        ]
        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None) -> TwitchClip:
        slug = self.parse_clip_url(url)
        return TwitchClip(slug)
