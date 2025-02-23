import re
from aiohttp import ClientSession
from bot.classes import BaseClip, BaseMisc, VideoTooLong, NoDuration, DownloadResponse
from typing import Optional


class TikTokMisc(BaseMisc):
    def __init__(self):
        super().__init__()
        self.platform_name = "TikTok"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        """
        Extracts the TikTok video ID from various URL formats.
        Returns None if the URL is not a valid TikTok video URL.
        """
        # Mathes URLs like:
        # - https://www.tiktok.com/@username/video/123456789
        # - https://m.tiktok.com/video/123456789
        # - https://vm.tiktok.com/video/123456789
        pattern = [
            r'(?:https?://)?(?:www\.|vm\.|m\.)?tiktok\.com/(?:@[^/]+/)?video/(\d+)',
            r'(?:https?://)?(?:www\.)?tiktok\.com/t/([A-Za-z0-9]+)/?'
        ]
        for p in pattern:
            match = re.match(p, url)
            if match:
                return match.group(1)
        return None

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'TikTokClip':
        video_id = self.parse_clip_url(url)
        if not video_id:
            self.logger.info(f"Invalid TikTok URL: {url}")
            raise NoDuration

        if re.match(r'(?:https?://)?(?:www\.)?tiktok\.com/t/([A-Za-z0-9]+)/?', url):
            # retrieve actual url
            async with ClientSession() as session:
                async with session.get(url) as response:
                    p = r'"canonical":"https:\\u002F\\u002Fwww\.tiktok\.com\\u002F@([\w.]+)\\u002Fvideo\\u002F(\d+)"'
                    txt = await response.text()
                    video_id, user = re.search(p, txt).group(2), re.search(p, txt).group(1)
                    url = f"https://www.tiktok.com/@{user}/video/{video_id}"
        else:
            # Extract username if available
            user_match = re.search(r'tiktok\.com/@([^/]+)/', url)
            user = user_match.group(1) if user_match else None

        # Verify video length (assuming all TikTok videos are short-form)
        valid = await self.is_shortform(
            url=url,
            basemsg=basemsg,
            cookies=cookies
        )
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        return TikTokClip(video_id, user)


class TikTokClip(BaseClip):
    def __init__(self, video_id, user):
        self._service = "tiktok"
        self._user = user
        self._video_id = video_id
        super().__init__(video_id)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        if self._user:
            return f"https://www.tiktok.com/@{self._user}/video/{self._video_id}"
        return f"https://www.tiktok.com/video/{self._video_id}"

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False) -> DownloadResponse:
        # download & upload to clyppy.io
        self.logger.info(f"({self.id}) run dl_download()...")
        local_file = await super().dl_download(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies
        )
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
