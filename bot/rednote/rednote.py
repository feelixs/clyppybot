from typing import Optional
from bot.classes import BaseMisc, BaseClip
import re


class RedMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "REDnote"

    def parse_clip_url(self, url: str) -> Optional[str]:
        if url.endswith("/"):
            url = url[:-1]  # remove trailing slash
        slug = str(url).split('/')[-1]
        if "?" in slug:
            slug = slug.split('?')[0]
        return slug

    def is_clip_link(self, url: str) -> bool:
        """
        Validates if a given URL is a valid Xiaohongshu post link.
        """
        patterns = [
            # Regular post pattern
            r'^https?://(?:www\.)?xiaohongshu\.com/discovery/item/[\w-]+',
            # Share link pattern
            r'^https?://(?:www\.)?xiaohongshu\.com/explore/[\w-]+'
        ]
        return any(bool(re.match(pattern, url)) for pattern in patterns)

    async def get_clip(self, url: str) -> Optional['RedClip']:
        slug = self.parse_clip_url(url)
        return RedClip(slug)


class RedClip(BaseClip):
    def __init__(self, slug):
        self._service = "rednote"
        self._url = f"https://xiaohongshu.com/explore/{slug}"
        super().__init__(slug)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url
