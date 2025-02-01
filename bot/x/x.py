import re
from bot.classes import BaseClip, BaseMisc, VideoTooLong
from typing import Optional

class Xmisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "Twitter"

    def parse_clip_url(self, url: str) -> str:
        """
        Extracts the tweet ID/slug from various Twitter URL formats.
        Returns None if the URL is not a valid Twitter URL.
        """
        patterns = [
            r'(?:https?://)?(?:www\.)?twitter\.com/\w+/status/(\d+)',
            r'(?:https?://)?(?:www\.)?x\.com/\w+/status/(\d+)',
        ]

        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str) -> 'Xclip':
        slug = self.parse_clip_url(url)
        valid = await self.is_shortform(url)
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        # Extract user from URL
        user_match = re.search(r'(?:twitter\.com|x\.com)/(\w+)/status/', url)
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

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False) -> Optional[DownloadResponse]:
        # download & upload to clyppy.io
        self.logger.info(f"({self.id}) Downloading and hosting on clyppy.io")
        local_file = await super().dl_download(filename, dlp_format, can_send_files)
        return await self.upload_to_clyppyio(local_file)
