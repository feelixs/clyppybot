import re

from interactions import Message, SlashContext
from bot.errors import VideoTooLong, NoDuration
from bot.classes import BaseClip, BaseMisc, is_discord_compatible
from bot.types import DownloadResponse
from typing import Optional, Union, Dict


class ClyppyioMisc(BaseMisc):
    def __init__(self, bot):
        super().__init__(bot)
        self.platform_name = None

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[str]:
        pattern = r'(?:https?://)?(?:www\.)?clyppy\.(io|com)/([a-z0-9]{8})'
        match = re.match(pattern, url)
        return match.group(2) if match else None

    async def is_shortform(self, url: str, basemsg: Union[Message, SlashContext], cookies=False, info=None) -> bool:
        d = info['duration']
        ...

    async def get_clyppy_clip(self, url) -> Dict:
        ...

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'ClyppyioClip':
        file_id = self.parse_clip_url(url)
        if not file_id:
            self.logger.info(f"Invalid Clyppy URL: {url}")
            raise NoDuration

        clip_info = await self.get_clyppy_clip(url)
        if not clip_info:
            self.logger.info(f"404 on Clyppy URL: {url}")
            raise NoDuration

        # Verify video length
        valid = await self.is_shortform(
            url=url,
            basemsg=basemsg,
            info=clip_info
        )
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        service = clip_info['service']
        self.platform_name = service
        return ClyppyioClip(clip_info, self.cdn_client, service.lower())


class ClyppyioClip(BaseClip):
    def __init__(self, data, cdn_client, service):
        self._service = service
        self.data = data
        self.clip_id = data['clip_id']
        super().__init__(self.clip_id, cdn_client)

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return 'https://clyppy.io/' + self.clip_id

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=True) -> DownloadResponse:
        return DownloadResponse(
            remote_url=self.url,
            local_file_path=None,
            duration=self.data['duration'],
            width=self.data['width'],
            height=self.data['height'],
            filesize=self.data['filesize'],
            video_name=self.data['video_name'],
            can_be_discord_uploaded=is_discord_compatible(self.data['filesize']) and can_send_files
        )
