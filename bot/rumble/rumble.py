import undetected_chromedriver as uc
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from typing import Optional
from bot.classes import BaseMisc, BaseClip
import re


class RumbleMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Rumble"

    def parse_clip_url(self, url: str) -> Optional[str]:
        if not url:
            return None

        # Handle embed URLs
        if "/embed/" in url:
            match = re.search(r'embed/v([^/?]+)', url)
            if match:
                return match.group(1)

        # Handle regular URLs
        match = re.search(r'/v([^/?]+)(?:\.html)?', url)
        if match:
            return match.group(1)

        return None

    def is_clip_link(self, url: str) -> bool:
        """
        Validates if a given URL is a valid Rumble video link.
        """
        patterns = [
            # Regular Rumble video pattern
            r'^https?://(?:www\.)?rumble\.com/v[\w-]+\.html',
            # Embedded Rumble video pattern
            r'^https?://(?:www\.)?rumble\.com/embed/v[\w-]+'
        ]
        return any(bool(re.match(pattern, url)) for pattern in patterns)

    async def get_clip(self, url: str) -> Optional['RumbleClip']:
        slug = self.parse_clip_url(url)
        is_embed = "/embed/" in url
        return RumbleClip(slug, is_embed)


class RumbleClip(BaseClip):
    def __init__(self, slug, is_embed):
        self._service = "rumble"
        if is_embed:
            self._url = f"https://rumble.com/embed/{slug}"
        else:
            self._url = f"https://rumble.com/{slug}"
        super().__init__(slug)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url
