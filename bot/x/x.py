import re
from bot.classes import BaseClip, BaseMisc, VideoTooLong, DownloadResponse
from typing import Optional

class Xmisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Twitter"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> str:
        """
        Extracts the tweet ID/slug from various Twitter URL formats.
        Returns None if the URL is not a valid Twitter URL.
        """
        patterns = [
            r'(?:https?://)?(?:www\.)?twitter\.com/\w+/status/(\d+)',
            r'(?:https?://)?(?:www\.)?x\.com/\w+/status/(\d+)',
        ]
        if extended_url_formats:
            patterns.extend([r'(?:https?://)?(?:www\.)?fxtwitter\.com/\w+/status/(\d+)',
                             r'(?:https?://)?(?:www\.)?fixupx\.com/\w+/status/(\d+)'])

        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str, extended_url_formats=False) -> 'Xclip':
        slug = self.parse_clip_url(url, extended_url_formats)
        valid = await self.is_shortform(url)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        # Extract user from URL
        user_match = re.search(r'(?:(?:fx)?twitter\.com|(?:fixup)?x\.com)/(\w+)/status/', url)
        user = user_match.group(1) if user_match else None

        return Xclip(slug, user)


class Xclip(BaseClip):
    def __init__(self, slug, user):
        self._service = "twitter"
        self._url = f"https://x.com/{user}/status/{slug}"
        super().__init__(slug)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return self._url

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False) -> DownloadResponse:
        # download & upload to clyppy.io
        self.logger.info(f"({self.id}) run dl_download()...")
        local_file = await super().dl_download(filename, dlp_format, can_send_files)
        if local_file.can_be_uploaded:
            return DownloadResponse(
                remote_url=None,
                local_file_path=local_file.local_file_path,
                duration=local_file.duration,
                width=local_file.width,
                height=local_file.height,
                filesize=local_file.filesize,
                video_name=local_file.video_name,
                can_be_uploaded=True
            )
        else:
            self.logger.info(f"({self.id}) hosting on clyppy.io...")
            return await self.upload_to_clyppyio(local_file)
