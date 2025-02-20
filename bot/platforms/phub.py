import re
from bot.classes import BaseClip, BaseMisc, VideoTooLong, NoDuration, DownloadResponse
from typing import Optional


class PhubMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "PornHub"
        self.is_nsfw = True

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        pattern = r'(?:https?://)?(?:www\.)?pornhub\.com/view_video\.php\?viewkey=([a-zA-Z0-9_-]+)'
        match = re.match(pattern, url)
        return match.group(1) if match else None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None) -> 'PhubClip':
        shortcode = self.parse_clip_url(url)
        if not shortcode:
            self.logger.info(f"Invalid URL: {url}")
            raise NoDuration

        valid = await self.is_shortform(url, basemsg)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        return PhubClip(shortcode)


class PhubClip(BaseClip):
    def __init__(self, shortcode):
        self._service = "pornhub"
        self._shortcode = shortcode
        super().__init__(shortcode)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return f"https://pornhub.com/view_video.php?viewkey={self._shortcode}"

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False) -> DownloadResponse:
        self.logger.info(f"({self.id}) run dl_download()...")
        dl = await super().dl_check_size(filename, dlp_format, can_send_files)
        if dl is not None:
            return dl
        return await super().download(filename=filename, dlp_format=dlp_format, can_send_files=can_send_files)
