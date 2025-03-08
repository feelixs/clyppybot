import re
from bot.classes import BaseClip, BaseMisc
from bot.types import DownloadResponse
from bot.errors import InvalidClipType, VideoTooLong
from typing import Optional


class R34Misc(BaseMisc):
    def __init__(self, bot):
        super().__init__(bot)
        self.platform_name = "Rule34Video"
        self.is_nsfw = True
        self.dl_timeout_secs = 180

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        pattern = r'(?:https?://)?(?:www\.)?rule34video\.co/watch/([a-zA-Z0-9_-]+)(?:/|$|\?)'
        match = re.match(pattern, url)
        return match.group(1) if match else None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'R34clip':
        slug = self.parse_clip_url(url, extended_url_formats)
        if slug is None:
            raise InvalidClipType
        valid = await self.is_shortform(
            url=url,
            basemsg=basemsg,
            cookies=cookies
        )
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        return R34clip(slug, self.cdn_client)


class R34clip(BaseClip):
    def __init__(self, slug, cdn_client):
        self._service = "rule34"
        self._url = f"https://rule34video.co/watch/{slug}/"
        super().__init__(slug, cdn_client)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False) -> DownloadResponse:
        self.logger.info(f"({self.id}) run dl_check_size(upload_if_large=True)...")
        return await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies,
            upload_if_large=True
        )
