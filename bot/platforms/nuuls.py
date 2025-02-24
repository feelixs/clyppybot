import re
from bot.classes import BaseClip, BaseMisc, VideoTooLong, NoDuration, DownloadResponse
from typing import Optional


class NuulsMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Nuuls"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        pattern = r'(?:https?://)?(?:[a-zA-Z0-9]+\.)?nuuls\.com/([a-zA-Z0-9_-]+\.[a-zA-Z0-9]+)(?:/|$|\?)'
        match = re.match(pattern, url)
        return match.group(1) if match else None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'NuulsClip':
        shortcode = self.parse_clip_url(url)
        if not shortcode:
            self.logger.info(f"Invalid Nuuls URL: {url}")
            raise NoDuration
        valid = await self.is_shortform(
            url=url,
            basemsg=basemsg,
            cookies=cookies
        )
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        return NuulsClip(shortcode)


class NuulsClip(BaseClip):
    def __init__(self, shortcode):
        self._service = "nuuls"
        self.filanem = shortcode
        super().__init__(shortcode)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return f"https://i.nuuls.com/{self.filanem}/"

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=True) -> DownloadResponse:
        self.logger.info(f"({self.id}) run dl_check_size()...")
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
