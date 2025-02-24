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
        # Pattern to match xvideos URLs like:
        # - https://www.xvideos.com/video.otkaofv96c8/39997451/0/title_here
        # - https://www.xvideos.com/video.uculeohe76f/drake
        pattern = r'(?:https?://)?(?:www\.)?xvideos\.com/video\.([a-z0-9]+)(?:/.*)?'
        match = re.match(pattern, url)
        return match.group(1) if match else None

    @staticmethod
    def get_vid_id(url: str) -> Optional[str]:
        # Extract the numeric ID if present in the URL
        pattern = r'(?:https?://)?(?:www\.)?xvideos\.com/video\.[a-z0-9]+/([0-9]+)(?:/.*)?'
        match = re.match(pattern, url)
        return match.group(1) if match else None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'XvidClip':
        first = self.parse_clip_url(url)
        if not first:
            self.logger.info(f"Invalid URL: {url}")
            raise NoDuration

        # The numeric ID might be optional in some URLs
        second = self.get_vid_id(url)
        if not second:
            second = "0"  # Default value if no numeric ID is found
            self.logger.info(f"No numeric ID found in URL: {url}, using default")

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
    def __init__(self, first, second=None):
        self._service = "xvideos"
        self._first = first
        self._second = second
        self._id = first if second is None or second == "0" else f"{first}/{second}"
        super().__init__(self._id)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        if self._second is None or self._second == "0":
            return f"https://xvideos.com/video.{self._first}"
        else:
            return f"https://xvideos.com/video.{self._first}/{self._second}"

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False) -> DownloadResponse:
        self.logger.info(f"({self.id}) run dl_check_size(upload_if_large=True)...")
        return await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies,
            upload_if_large=True
        )
