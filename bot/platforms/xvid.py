import re
from bot.classes import BaseClip, BaseMisc, VideoTooLong, NoDuration, DownloadResponse
from typing import Optional


class XvidMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Xvideos"
        self.is_nsfw = True
        self.dl_timeout_secs = 120

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        pattern = r'(?:https?://)?(?:www\.)?xvideos\.com/video\.([a-z0-9]+)/[0-9]+/[0-9]/[a-zA-Z0-9_-]+'
        match = re.match(pattern, url)
        return match.group(1) if match else None

    @staticmethod
    def get_vid_id(url: str) -> Optional[str]:
        pattern = r'(?:https?://)?(?:www\.)?xvideos\.com/video\.[a-z0-9]+/([0-9]+)/[0-9]/[a-zA-Z0-9_-]+'
        match = re.match(pattern, url)
        return match.group(1) if match else None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'XvidClip':
        first, second = self.parse_clip_url(url), self.get_vid_id(url)
        if not first or not second:
            self.logger.info(f"Invalid URL: {url}")
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

        return XvidClip(first, second)


class XvidClip(BaseClip):
    def __init__(self, first, second):
        self._service = "xvideos"
        self._id = f"{first}/{second}"
        super().__init__(self._id)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return f"https://xvideos.com/video.{self._id}"

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False) -> DownloadResponse:
        self.logger.info(f"({self.id}) run dl_check_size(upload_if_large=True)...")
        return await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies,
            upload_if_large=True
        )
