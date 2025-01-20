from typing import Optional
from bot.classes import BaseMisc, BaseClip
import re


class ImgurMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Imgur"

    def parse_clip_url(self, url: str) -> Optional[str]:
        if url.endswith("/"):
            url = url[:-1]  # remove trailing slash
        slug = str(url).split('/')[-1]
        if "?" in slug:
            slug = slug.split('?')[0]
        return slug

    def is_clip_link(self, url: str) -> bool:
        """
       Validates if a given URL is a valid Imgur post/album/gallery link.
       """
        patterns = [
            # Image direct link
            r'^https?://(?:i\.)?imgur\.com/[\w]{5,7}(?:\.(?:jpg|gif|png|mp4))?$',
            # Album/gallery links
            r'^https?://(?:www\.)?imgur\.com/(?:a|gallery)/[\w]{5,7}$',
            # Single image page
            r'^https?://(?:www\.)?imgur\.com/[\w]{5,7}$'
        ]
        return any(bool(re.match(pattern, url)) for pattern in patterns)

    async def get_clip(self, url: str) -> Optional['ImgurClip']:
        slug = self.parse_clip_url(url)
        return ImgurClip(slug)


class ImgurClip(BaseClip):
    def __init__(self, slug):
        self._service = "imgur"
        self._url = f"https://imgur.com/{slug}"
        super().__init__(slug)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url
