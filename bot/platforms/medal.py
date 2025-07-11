from bot.classes import BaseClip, DownloadResponse
from bot.classes import BaseMisc
from typing import Optional
import re


class MedalMisc(BaseMisc):
    def __init__(self, bot):
        super().__init__(bot)
        self.platform_name = "Medal"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
        Parses a Medal.tv clip URL to extract just the clip ID.

        Example:
        "https://medal.tv/games/game/clips/abc123/xyz789" -> "abc123"
        "https://medal.tv/clips/abc123" -> "abc123"
        """
        patterns = [
            # Full game path pattern
            r'^(?:https?://)?(?:www\.)?medal\.tv/games/[\w-]+/clips/([\w-]+)',
            # Short clip pattern
            r'^(?:https?://)?(?:www\.)?medal\.tv/clips/([\w-]+)'
        ]

        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'MedalClip':
        # todo run is_shortform here
        slug = self.parse_clip_url(url)
        return MedalClip(slug, self.cdn_client, 0)


class MedalClip(BaseClip):
    def __init__(self, slug, cdn_client, tokens_used: int):
        self._service = "medal"
        self._url = f"https://medal.tv/clips/{slug}"
        # pass dummy duration because we haven't added is_valid (is_shortform) for medal links
        super().__init__(slug, cdn_client, tokens_used, 0)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False) -> DownloadResponse:
        dl = await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies
        )
        if dl is not None:
            return dl
        return await super().download(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies
        )
