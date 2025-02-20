from bot.classes import BaseMisc
from bot.platforms.kick import KickClip
import re


class KickMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Kick"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> (str, str):
        user = url.split('kick.com/')[-1].split("/")[0]
        if "?" in user:
            user = user.split("?")[0]
        if url.endswith("/"):
            url = url[:-1]  # remove trailing slash
        slug = str(url).split('/')[-1]
        if "?clip=" in slug:
            slug = slug.split("=")[-1]
        elif "?" in slug:
            slug = slug.split('?')[0]
        slug = slug.replace("clip_", "")
        return slug, user

    def is_clip_link(self, url: str) -> bool:
        # Pattern matches both:
        # https://kick.com/[username]/clips/[clip-id]
        # https://kick.com/[username]?clip=[clip-id]
        clip_pattern = r'^https?://(?:www\.)?kick\.com/[a-zA-Z0-9_-]+/clips/clip_[a-zA-Z0-9]+'
        query_pattern = r'^https?://(?:www\.)?kick\.com/[a-zA-Z0-9_-]+\?clip=clip_[a-zA-Z0-9]+'
        return bool(re.match(clip_pattern, url) or re.match(query_pattern, url))

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None) -> KickClip:
        slug, user = self.parse_clip_url(url)
        return KickClip(slug, user)
