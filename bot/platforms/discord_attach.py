import re
from bot.classes import BaseClip, BaseMisc
from bot.errors import VideoTooLong, NoDuration
from bot.types import DownloadResponse
from typing import Optional, Dict


class DiscordMisc(BaseMisc):
    def __init__(self, bot):
        super().__init__(bot)
        self.platform_name = "Discord"

    def parse_clip_url(self, url: str, extended_url_formats=False) -> Optional[Dict]:
        pattern = r'(?:https?://)?(?:www\.)?cdn\.discordapp\.com/attachments/(\d+)/(\d+)/([^?]+)(?:\?(.+))?'
        match = re.match(pattern, url)

        if not match:
            return None

        return {
            'channel': match.group(1),
            'some_id': match.group(2),
            'filename': match.group(3),
            'url_params': match.group(4)
        }

    async def get_clip(self, url: str, extended_url_formats=False, basemsg=None, cookies=False) -> 'DiscordAttachment':
        attrs = self.parse_clip_url(url)
        the_id, chn, filename, ext = attrs.get('some_id'), attrs.get('channel'), attrs.get('filename'), attrs.get('url_params')
        if not the_id or not chn or not filename or not ext:
            self.logger.info(f"Invalid Discord URL: {url}")
            raise NoDuration

        valid, tokens_used = await self.is_shortform(
            # todo check if file is video file
            url=url,
            basemsg=basemsg,
            cookies=cookies
        )
        if not valid:
            self.logger.info(f"{url} is_shortform=False")
            raise VideoTooLong
        self.logger.info(f"{url} is_shortform=True")

        attrs['message_id'] = basemsg.id
        attrs['cdn_client'] = self.cdn_client
        attrs['tokens_used'] = tokens_used
        return DiscordAttachment(attrs)


class DiscordAttachment(BaseClip):
    def __init__(self, attrs: Dict):
        self._service = "discord"
        self.cdn_client = attrs.get('cdn_client')
        self._message_id = attrs.get('message_id')
        self._some_id = attrs.get('some_id')
        self._channel = attrs.get('channel')
        self._filename = attrs.get('filename')
        self._url_params = attrs.get('url_params')
        super().__init__(self._message_id, self.cdn_client, attrs.get('tokens_used'))

    @property
    def service(self) -> str:
        return self._service

    @property
    def url(self) -> str:
        return f"https://cdn.discordapp.com/attachments/{self._channel}/{self._some_id}/{self._filename}?{self._url_params}"

    async def download(self, filename=None, dlp_format='best/bv*+ba', can_send_files=False, cookies=False) -> DownloadResponse:
        self.logger.info(f"({self.url}) run dl_check_size(upload_if_large=True)...")
        return await super().dl_check_size(
            filename=filename,
            dlp_format=dlp_format,
            can_send_files=can_send_files,
            cookies=cookies,
            upload_if_large=True
        )
