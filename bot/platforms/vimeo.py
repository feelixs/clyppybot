import re
from bot.classes import BaseClip, BaseMisc, VideoTooLong, NoDuration, DownloadResponse
from typing import Optional


class VimeoMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Vimeo"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
        Extracts the Vimeo video ID from various URL formats.
        Returns None if the URL is not a valid Vimeo video URL.
        """
        # Matches URLs like:
        # - https://vimeo.com/123456789
        # - https://vimeo.com/123456789?query=param
        # - https://www.vimeo.com/123456789
        # - https://vimeo.com/user1234/123456789
        pattern = r'(?:https?://)?(?:www\.)?vimeo\.com/(?:[\w-]+/)?(\d+)(?:$|\?|/)'
        match = re.search(pattern, url)
        return match.group(1) if match else None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None) -> 'VimeoClip':
        video_id = self.parse_clip_url(url)
        if not video_id:
            self.logger.info(f"Invalid Vimeo URL: {url}")
            raise NoDuration

        # Verify video length
        valid = await self.is_shortform(url, basemsg)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        return VimeoClip(video_id)


class VimeoClip(BaseClip):
    def __init__(self, video_id):
        self._service = "vimeo"
        self._video_id = video_id
        super().__init__(video_id)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return f"https://vimeo.com/{self._video_id}"

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False) -> DownloadResponse:
        self.logger.info(f"({self.id}) run dl_check_size(upload_if_large=True)...")
        return await super().dl_check_size(filename, dlp_format, can_send_files, upload_if_large=True)
