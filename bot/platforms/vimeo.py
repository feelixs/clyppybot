import re
from bot.classes import BaseClip, BaseMisc, VideoTooLong, NoDuration, DownloadResponse
from typing import Optional


class VimeoMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Vimeo"
        self.dl_timeout_secs = 120

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
        Extracts the main video ID from a Vimeo URL.
        Works with all supported URL formats.
        """
        patterns = [
            r'^(?:https?://)?(?:www\.)?vimeo\.com/(\d+)(?:/[a-zA-Z0-9]+)?(?:\?|$)',
            r'^(?:https?://)?(?:www\.)?vimeo\.com/[\w-]+/(\d+)(?:/[a-zA-Z0-9]+)?(?:\?|$)'
        ]
        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def get_clip_hash(url: str) -> Optional[str]:
        """
        Extracts the secondary hash ID from a Vimeo URL if present.
        """
        patterns = [
            r'^(?:https?://)?(?:www\.)?vimeo\.com/\d+/([a-zA-Z0-9]+)(?:\?|$)',
            r'^(?:https?://)?(?:www\.)?vimeo\.com/[\w-]+/\d+/([a-zA-Z0-9]+)(?:\?|$)'
        ]
        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None) -> 'VimeoClip':
        video_id, video_hash = self.parse_clip_url(url), self.get_clip_hash(url)
        if not video_id:
            self.logger.info(f"Invalid Vimeo URL: {url}")
            raise NoDuration

        # Verify video length
        valid = await self.is_shortform(url, basemsg)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        return VimeoClip(video_id, video_hash)


class VimeoClip(BaseClip):
    def __init__(self, video_id, video_hash):
        self._service = "vimeo"
        self._video_id = f'{video_id}/{video_hash}'
        self._url = f"https://vimeo.com/{self._video_id}"
        super().__init__(video_id)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False) -> DownloadResponse:
        self.logger.info(f"({self.id}) run dl_check_size(upload_if_large=True)...")
        return await super().dl_check_size(filename, dlp_format, can_send_files, upload_if_large=True)
