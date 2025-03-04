import re
from bot.types import DownloadResponse
from bot.errors import VideoTooLong, NoDuration
from bot.classes import BaseClip, BaseMisc
from typing import Optional


class XvidMisc(BaseMisc):
    def __init__(self, bot):
        super().__init__(bot)
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

    @staticmethod
    def get_title(url: str) -> Optional[str]:
        # Extract the title part if present
        pattern = r'(?:https?://)?(?:www\.)?xvideos\.com/video\.[a-z0-9]+(?:/[0-9]+(?:/[0-9]+)?)?/([^/?]+)'
        match = re.match(pattern, url)
        return match.group(1) if match else None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'XvidClip':
        first = self.parse_clip_url(url)
        if not first:
            self.logger.info(f"Invalid URL: {url}")
            raise NoDuration

        second = self.get_vid_id(url)
        title = self.get_title(url)

        valid = await self.is_shortform(
            url=url,
            basemsg=basemsg,
            cookies=cookies
        )
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        return XvidClip(first, second, title, self.cdn_client)


class XvidClip(BaseClip):
    def __init__(self, first, second=None, title=None, cdn_client=None):
        self._service = "xvideos"
        self._first = first
        self._second = second
        self._title = title

        # For internal ID tracking
        self._id = first if second is None or second == "0" else f"{first}/{second}"
        super().__init__(self._id, cdn_client)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        if self._title:
            if self._second and self._second != "0":
                return f"https://xvideos.com/video.{self._first}/{self._second}/0/{self._title}"
            else:
                return f"https://xvideos.com/video.{self._first}/{self._title}"
        else:
            # Fallback if no title
            if self._second and self._second != "0":
                return f"https://xvideos.com/video.{self._first}/{self._second}"
            else:
                return f"https://xvideos.com/video.{self._first}"

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False,
                       cookies=False) -> DownloadResponse:
        self.logger.info(f"({self.id}) run dl_check_size(upload_if_large=True)...")
        return await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies,
            upload_if_large=True
        )
